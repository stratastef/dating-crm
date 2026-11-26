"""The review queue: items that wait for the user, and the live push for the hot ones."""

from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import calendar, paid_items
from app.auth import CurrentUser, Db
from app.drafts import DRAFT_COLUMNS, Draft, present
from app.push import send_push

router = APIRouter()

_LONG_AGO = datetime.min.replace(tzinfo=UTC)

# The item kind of a draft that waits for the user, by the draft's status.
_DRAFT_KINDS = {"pending": "draft", "copied": "copied_draft", "failed": "failed_send"}


class QuotedMessage(BaseModel):
    body: str
    sent_at: datetime


class QueueItem(BaseModel):
    kind: str  # `draft`, `copied_draft`, `failed_send`, `handover` or `paid_item`
    hot: bool
    card_id: int | None  # null when `kind` is `paid_item`: a swipe candidate is not a card
    card_name: str
    # The card summary, `Card` in `app/cards.py` (a dict here: that module imports this one). Null when
    # `card_id` is.
    card: dict | None = None
    draft: Draft | None  # set when `kind` is `draft`, `copied_draft` or `failed_send`
    # The match's message the item is about: the one a reply draft answers, or the one that fired a handover.
    # Null for an opener and a paid item.
    message: QuotedMessage | None = None
    # Set when `kind` is `handover`: the handover checks `message` hit (`HANDOVER` in `app/jev.py`, or
    # `unavailable` when Jev could not be asked). Null when no hit is stored.
    triggers: list[str] | None = None
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
    """Call when an item joins the queue. A hot lead is pushed at once; the rest waits in the queue silently.

    The push shows on the lock screen, so without the user's name previews it names nobody and quotes nothing.
    """
    if is_hot_lead(db, user_id, card_id):
        previews = db.execute(text("SELECT push_name_previews FROM users WHERE id = :id"), {"id": user_id}).scalar_one()
        if not previews:
            title, body = "Hot lead", "Someone replied. A draft is ready."
        send_push(db, user_id, title, body or f"A draft for {name} is waiting for you", card_id=card_id)


@router.get("/queue", response_model=list[QueueItem])
def queue(user: CurrentUser, db: Db):
    """Everything that waits for the user: hot leads first, then oldest first."""
    # Each item with the time it began to wait. A new kind of item adds its own loop.
    waiting: list[tuple[datetime, QueueItem]] = []
    # A reply answers the newest message the match had sent when it was written.
    drafts = db.execute(
        text(
            f"""
            SELECT {", ".join(f"drafts.{column}" for column in DRAFT_COLUMNS.split(", "))},
                   drafts.copied_at, drafts.updated_at,
                   cards.name AS card_name, answered.body AS message_body, answered.sent_at AS message_sent_at
            FROM drafts JOIN cards ON cards.id = drafts.card_id
            LEFT JOIN LATERAL (
                SELECT body, sent_at FROM messages
                WHERE messages.card_id = drafts.card_id AND messages.user_id = :user_id AND sender = 'them'
                  AND drafts.kind = 'reply' AND sent_at <= drafts.created_at
                ORDER BY sent_at DESC, id DESC LIMIT 1
            ) answered ON true
            WHERE drafts.user_id = :user_id AND drafts.status IN ('pending', 'copied', 'failed')
            ORDER BY drafts.created_at, drafts.id
            """
        ),
        {"user_id": user.id},
    ).all()
    # The trigger is the newest message from the match that hit a handover check.
    handovers = db.execute(
        text(
            """
            SELECT cards.id, cards.name, cards.handover_suggestions, hit.handover AS triggers,
                   hit.body AS message_body, hit.sent_at AS message_sent_at
            FROM cards LEFT JOIN LATERAL (
                SELECT handover, body, sent_at FROM messages
                WHERE messages.card_id = cards.id AND messages.user_id = :user_id AND sender = 'them'
                  AND cardinality(handover) > 0
                ORDER BY sent_at DESC, id DESC LIMIT 1
            ) hit ON true
            WHERE cards.user_id = :user_id AND cards.handover = 'pending' ORDER BY cards.id
            """
        ),
        {"user_id": user.id},
    ).all()
    cards = _summaries(db, user.id, [row.card_id for row in drafts] + [row.id for row in handovers])
    for row, draft in zip(drafts, present(db, user.id, drafts), strict=True):
        item = QueueItem(
            kind=_DRAFT_KINDS[row.status],
            hot=cards[row.card_id]["hot"],
            card_id=row.card_id,
            card_name=row.card_name,
            card=cards[row.card_id],
            draft=draft,
            message=_quoted(row),
        )
        # A copied draft waits from when it was copied, a failed send from when it failed.
        waiting.append((row.updated_at if row.status == "failed" else row.copied_at or row.created_at, item))
    for row in handovers:
        item = QueueItem(
            kind="handover",
            hot=cards[row.id]["hot"],
            card_id=row.id,
            card_name=row.name,
            card=cards[row.id],
            draft=None,
            message=_quoted(row),
            triggers=row.triggers,
            suggestions=row.handover_suggestions,
        )
        # shortcut: the trigger message's time stands in for when the handover began (a card paused before
        # the trigger was stored counts as oldest). Store the start on the card if the two drift apart.
        waiting.append((row.message_sent_at or _LONG_AGO, item))
    for row in paid_items.waiting(db, user.id):
        item = QueueItem(
            kind="paid_item",
            hot=False,  # a paid item is never hot
            card_id=None,
            card_name=row.name,
            draft=None,
            paid_item=paid_items.Proposal(**row._mapping),
        )
        waiting.append((row.created_at, item))
    return [item for _, item in sorted(waiting, key=lambda pair: (not pair[1].hot, pair[0]))]


def _summaries(db: Connection, user_id: int, card_ids: list[int]) -> dict[int, dict]:
    """The card summaries of the user's cards, by card id."""
    from app.cards import CARD_COLUMNS, summarize  # imported here: app.cards imports this module for `is_hot_lead`

    rows = db.execute(
        text(f"SELECT {CARD_COLUMNS} FROM cards WHERE user_id = :user_id AND id = ANY(:ids)"),
        {"user_id": user_id, "ids": card_ids},
    ).all()
    return {card.id: card.model_dump() for card in summarize(db, user_id, rows)}


def _quoted(row) -> QuotedMessage | None:
    return QuotedMessage(body=row.message_body, sent_at=row.message_sent_at) if row.message_body is not None else None


def _decide(db: Connection, user_id: int, draft_id: int, status: str, allowed: tuple[str, ...]) -> Draft:
    """Move the draft from one of the `allowed` statuses to `status`. 404 if it is not the user's, 409 if it is
    in another status."""
    row = db.execute(
        text(
            f"""
            UPDATE drafts SET status = :status, updated_at = now(),
                copied_at = CASE WHEN :status = 'copied' THEN now() ELSE copied_at END
            WHERE id = :id AND user_id = :user_id AND status = ANY(:allowed)
            RETURNING {DRAFT_COLUMNS}
            """
        ),
        {"id": draft_id, "user_id": user_id, "status": status, "allowed": list(allowed)},
    ).one_or_none()
    if not row:
        now = db.execute(
            text("SELECT status FROM drafts WHERE id = :id AND user_id = :user_id"), {"id": draft_id, "user_id": user_id}
        ).scalar_one_or_none()
        if now:
            raise HTTPException(status_code=409, detail=f"the draft is {now}")
        raise HTTPException(status_code=404, detail="draft not found")
    return present(db, user_id, [row])[0]


@router.post("/drafts/{draft_id}/copy", response_model=Draft)
def copy_draft(draft_id: int, user: CurrentUser, db: Db):
    """The user copied a pending or failed draft to send it by hand, on any card. It waits in Review as
    `copied_draft` until a newer message from the user appears on its card (`insert_message()` in `app/cards.py`)."""
    return _decide(db, user.id, draft_id, "copied", ("pending", "failed"))


@router.post("/drafts/{draft_id}/dismiss", response_model=Draft)
def dismiss_draft(draft_id: int, user: CurrentUser, db: Db):
    """Drop a pending draft from the queue, or clear a copied or failed one. Nothing is sent, so the slots the
    draft offered are free again."""
    draft = _decide(db, user.id, draft_id, "dismissed", ("pending", "copied", "failed"))
    try:
        calendar.release_holds(
            db, user.id, draft.card_id, trigger=f"copilot: user dismissed draft {draft.id}", draft_id=draft.id
        )
    except httpx.HTTPError:
        # Raising rolls the dismissal back, so the draft and the calendar stay in step.
        raise HTTPException(status_code=502, detail="Google Calendar could not be reached; try again")
    return draft
