"""The review queue: items that wait for the user, and the live push for the hot ones."""

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import calendar, paid_items
from app.auth import CurrentUser, Db
from app.drafts import _COLUMNS as _DRAFT_COLUMNS
from app.drafts import Draft
from app.push import send_push

router = APIRouter()


class QueueItem(BaseModel):
    kind: str  # `draft`, `handover` or `paid_item`
    hot: bool
    card_id: int | None  # null when `kind` is `paid_item`: a swipe candidate is not a card
    card_name: str
    draft: Draft | None  # set when `kind` is `draft`
    suggestions: list[str] | None = None  # set when `kind` is `handover`: the suggested replies
    paid_item: paid_items.Proposal | None = None  # set when `kind` is `paid_item`


def is_hot_lead(db: Connection, user_id: int, card_id: int) -> bool:
    """The only definition of a hot lead: the match replied within the last hour, Jev's hot-lead triage
    flagged a pending draft of the card (`drafts.hot_lead`, see `app/jev.py`), the card waits for the user
    after a handover trigger (`cards.handover` is `pending`, see `app/handover.py`), or a date is being
    coordinated: a slot is held for the match, or a message of theirs about logistics is unanswered.
    """
    return db.execute(
        text(
            """
            SELECT EXISTS (SELECT 1 FROM messages WHERE card_id = :card_id AND user_id = :user_id
                           AND sender = 'them' AND sent_at > now() - interval '1 hour')
                OR EXISTS (SELECT 1 FROM drafts WHERE card_id = :card_id AND user_id = :user_id
                           AND status = 'pending' AND hot_lead)
                OR EXISTS (SELECT 1 FROM cards WHERE id = :card_id AND user_id = :user_id AND handover = 'pending')
                OR EXISTS (SELECT 1 FROM calendar_holds WHERE card_id = :card_id AND user_id = :user_id
                           AND status = 'held')
                OR EXISTS (SELECT 1 FROM messages WHERE card_id = :card_id AND user_id = :user_id
                           AND sender = 'them' AND 'logistics' = ANY(handover)
                           AND sent_at > coalesce((SELECT max(sent_at) FROM messages WHERE card_id = :card_id
                                                   AND user_id = :user_id AND sender = 'me'), '-infinity'))
            """
        ),
        {"card_id": card_id, "user_id": user_id},
    ).scalar_one()


def notify_if_hot(
    db: Connection, user_id: int, card_id: int, name: str, title: str = "Hot lead", body: str | None = None
) -> None:
    """Call when an item joins the queue. A hot lead is pushed at once; the rest waits in the queue silently."""
    if is_hot_lead(db, user_id, card_id):
        send_push(db, user_id, title, body or f"A draft for {name} is waiting for you", card_id=card_id)


def hand_on_approved_draft(db: Connection, user_id: int, draft: Draft) -> None:
    """Called once for each draft the user approves: queues its send when the card's app can send."""
    from app.send import send_approved  # imported here: app.send imports app.cards, which leads back to this module

    send_approved(db, user_id, draft.id, trigger=f"copilot: user approved draft {draft.id}")


@router.get("/queue", response_model=list[QueueItem])
def queue(user: CurrentUser, db: Db):
    """Everything that waits for the user: hot leads first, then oldest first."""
    rows = db.execute(
        text(
            f"""
            SELECT {", ".join(f"drafts.{column}" for column in _DRAFT_COLUMNS.split(", "))}, cards.name AS card_name
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
            hot=is_hot_lead(db, user.id, row.card_id),
            card_id=row.card_id,
            card_name=row.card_name,
            draft=Draft.model_validate(row, from_attributes=True),
        )
        for row in rows
    ]
    handovers = db.execute(
        text(
            "SELECT id, name, handover_suggestions FROM cards"
            " WHERE user_id = :user_id AND handover = 'pending' ORDER BY id"
        ),
        {"user_id": user.id},
    ).all()
    # shortcut: handovers come before drafts, not by age. Store when the handover began if that order matters.
    items = [
        QueueItem(
            kind="handover",
            hot=is_hot_lead(db, user.id, row.id),
            card_id=row.id,
            card_name=row.name,
            draft=None,
            suggestions=row.handover_suggestions,
        )
        for row in handovers
    ] + items
    # Paid items are never hot, so they come after the hot leads.
    items = [
        QueueItem(kind="paid_item", hot=False, card_id=None, card_name=row.name, draft=None, paid_item=row._mapping)
        for row in paid_items.waiting(db, user.id)
    ] + items
    return sorted(items, key=lambda item: not item.hot)  # stable, so each group stays oldest first


def _decide(db: Connection, user_id: int, draft_id: int, status: str) -> Draft:
    """Move a pending draft to `status`. 404 if it is not the user's, 409 if it was decided before."""
    row = db.execute(
        text(
            f"""
            UPDATE drafts SET status = :status, updated_at = now()
            WHERE id = :id AND user_id = :user_id AND status = 'pending'
            RETURNING {_DRAFT_COLUMNS}
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
    """Drop a pending draft from the queue. Nothing is sent, so the slots the draft offered are free again."""
    draft = _decide(db, user.id, draft_id, "dismissed")
    try:
        calendar.release_holds(
            db, user.id, draft.card_id, trigger=f"copilot: user dismissed draft {draft.id}", draft_id=draft.id
        )
    except httpx.HTTPError:
        # Raising rolls the dismissal back, so the draft and the calendar stay in step.
        raise HTTPException(status_code=502, detail="Google Calendar could not be reached; try again")
    return draft
