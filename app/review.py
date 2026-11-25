"""The review queue: items that wait for the user, and the live push for the hot ones."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db
from app.push import send_push

router = APIRouter()

_DRAFT_COLUMNS = ("id", "card_id", "kind", "status", "original", "edited")


class Draft(BaseModel):
    """Same shape as the draft the routes in `app/drafts.py` return."""

    id: int
    card_id: int
    kind: str
    status: str
    original: str
    edited: str | None


class QueueItem(BaseModel):
    kind: str  # `draft` so far; handovers and paid-item approvals join later with their own kind
    hot: bool
    card_id: int
    card_name: str
    draft: Draft | None  # set when `kind` is `draft`


def is_hot_lead(db: Connection, card_id: int) -> bool:
    """The only definition of a hot lead. So far: the match replied within the last hour.

    Date coordination and handovers are also hot (see the spec); add those signals here.
    """
    return db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM messages WHERE card_id = :card_id AND sender = 'them'"
            " AND sent_at > now() - interval '1 hour')"
        ),
        {"card_id": card_id},
    ).scalar_one()


def notify_if_hot(db: Connection, user_id: int, card_id: int, name: str) -> None:
    """Call when an item joins the queue. A hot lead is pushed at once; the rest waits in the queue silently."""
    if is_hot_lead(db, card_id):
        send_push(db, user_id, "Hot lead", f"A draft for {name} is waiting for you", card_id=card_id)


def hand_on_approved_draft(db: Connection, user_id: int, draft: Draft) -> None:
    """Called once for each draft the user approves. Sending it through the app's connector goes here."""


@router.get("/queue", response_model=list[QueueItem])
def queue(user: CurrentUser, db: Db):
    """Everything that waits for the user: hot leads first, then oldest first."""
    rows = db.execute(
        text(
            f"""
            SELECT {", ".join(f"drafts.{column}" for column in _DRAFT_COLUMNS)}, cards.name AS card_name
            FROM drafts JOIN cards ON cards.id = drafts.card_id
            WHERE drafts.user_id = :user_id AND drafts.status = 'pending'
            ORDER BY drafts.created_at, drafts.id
            """
        ),
        {"user_id": user.id},
    ).all()
    # shortcut: one hot-lead query per item, fold into the query above if queues get long.
    items = [
        QueueItem(
            kind="draft",
            hot=is_hot_lead(db, row.card_id),
            card_id=row.card_id,
            card_name=row.card_name,
            draft=Draft.model_validate(row, from_attributes=True),
        )
        for row in rows
    ]
    return sorted(items, key=lambda item: not item.hot)  # stable, so each group stays oldest first


def _decide(db: Connection, user_id: int, draft_id: int, status: str) -> Draft:
    """Move a pending draft to `status`. 404 if it is not the user's, 409 if it was decided before."""
    row = db.execute(
        text(
            f"""
            UPDATE drafts SET status = :status, updated_at = now()
            WHERE id = :id AND user_id = :user_id AND status = 'pending'
            RETURNING {", ".join(_DRAFT_COLUMNS)}
            """
        ),
        {"id": draft_id, "user_id": user_id, "status": status},
    ).one_or_none()
    if not row:
        exists = db.execute(
            text("SELECT 1 FROM drafts WHERE id = :id AND user_id = :user_id"), {"id": draft_id, "user_id": user_id}
        ).one_or_none()
        if exists:
            raise HTTPException(status_code=409, detail="draft already decided")
        raise HTTPException(status_code=404, detail="draft not found")
    return Draft.model_validate(row, from_attributes=True)


@router.post("/drafts/{draft_id}/approve", response_model=Draft)
def approve_draft(draft_id: int, user: CurrentUser, db: Db):
    """Approve a pending draft as it stands (the user's edit, if any) and hand it on."""
    draft = _decide(db, user.id, draft_id, "approved")
    hand_on_approved_draft(db, user.id, draft)
    return draft


@router.post("/drafts/{draft_id}/dismiss", response_model=Draft)
def dismiss_draft(draft_id: int, user: CurrentUser, db: Db):
    """Drop a pending draft from the queue. Nothing is sent."""
    return _decide(db, user.id, draft_id, "dismissed")
