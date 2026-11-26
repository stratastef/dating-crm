"""Match cards: one card per match, moving through the pipeline stages."""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, computed_field, field_validator
from sqlalchemy import Connection, Row, text
from sqlalchemy.exc import IntegrityError

from app import calendar, handover, tombstones
from app.auth import CurrentUser, Db
from app.autopilot import autopilot_allowed
from app.card_lookup import own_card
from app.drafts import _COLUMNS as _DRAFT_COLUMNS
from app.drafts import Draft, present
from app.jobs import enqueue, handler
from app.review import is_hot_lead
from app.voice import queue_profile

router = APIRouter()

# The seven pipeline stages, in order. The `cards.stage` check constraint lists the same values.
Stage = Literal["matched", "chatting", "number_swapped", "date_set", "dated", "seeing_them", "archived"]

_COLUMNS = (
    "id, app, external_id, name, stage, stage_changed_at, notes, next_action, due_date, created_at,"
    " stalled_at IS NOT NULL AS stalled, date_rating, date_note, handover, handover_suggestions,"
    " led_to_date, ai_disclosed, topic"
)

# Only cards in these stages can be Stalled. Stalled is a flag (`cards.stalled_at`), not a stage.
_STALLABLE = "('chatting', 'number_swapped', 'date_set')"


@handler("mark_stalled", every=timedelta(hours=1))
def mark_stalled(db: Connection, user_id: int, payload: dict) -> None:
    """Flag the user's cards whose last message, from either side, is older than their `stalled_after_days`."""
    # A card with no messages counts from its last stage change.
    db.execute(
        text(
            f"""
            UPDATE cards SET stalled_at = now()
            FROM users
            WHERE users.id = :user_id AND cards.user_id = users.id
              AND cards.stalled_at IS NULL AND cards.stage IN {_STALLABLE}
              AND COALESCE(
                    (SELECT max(sent_at) FROM messages WHERE messages.card_id = cards.id), cards.stage_changed_at
                  ) < now() - make_interval(days => users.stalled_after_days)
            """
        ),
        {"user_id": user_id},
    )


def is_good_date(rating: int | None) -> bool:
    """The only definition of a good date: a rating of 4 or 5. An unrated date is not one."""
    return rating is not None and rating >= 4


class LastMessage(BaseModel):
    sender: str  # `me` or `them`
    body: str  # the first 100 characters
    sent_at: datetime


class Card(BaseModel):
    """A card with its card summary: everything a row in the app shows, so the app makes no other call.

    Every card response is built by `summarize()`.
    """

    id: int
    app: str
    external_id: str | None
    name: str
    stage: str
    stage_changed_at: datetime
    notes: str
    next_action: str | None
    due_date: date | None
    created_at: datetime
    stalled: bool
    date_rating: int | None
    date_note: str | None
    # Paused for handover (see `app/handover.py`): `pending`, `taken_over` or null.
    handover: str | None
    handover_suggestions: list[str]
    # Outcome label of the chat: the card was once in `date_set`, `dated` or `seeing_them`, or has a rating.
    led_to_date: bool
    # A message that carried the AI disclosure was sent to this match (see `app/send.py`).
    ai_disclosed: bool
    # The card summary. The newest message by `sent_at`, from either side; null when there are none.
    last_message: LastMessage | None
    hot: bool  # a hot lead: `is_hot_lead()` in `app/review.py`, as on the review queue
    pending_draft: Draft | None  # the newest pending draft, the one the review queue shows; null when none
    drafts: list[Draft]  # the card's draft list: its pending, copied and failed drafts, newest first
    lead_photo_url: str | None  # the first photo attached to the card; null when unknown
    # Where the Pipeline lists the card, and why: see `app/pipeline.py`.
    pipeline_group: str  # a `Group`: `waiting_for_you`, `handled_by_autopilot`, ...
    reason: str | None  # a `Reason` when the card is Waiting for you, else null
    handover_trigger: str | None  # with reason `handover`: the handover check that hit, such as `logistics`
    autopilot_activity: str | None  # an `Activity` when the card is Handled by autopilot, else null
    # What the chat is about, in a few words ("museums"): written with the card's latest draft, empty before one.
    topic: str

    @computed_field
    @property
    def suggested_actions(self) -> list[str]:
        """What the app offers on a Stalled card. `archive` is `PATCH /cards/{id}` with `stage: archived`."""
        return ["revive", "archive"] if self.stalled else []

    @computed_field
    @property
    def good_date(self) -> bool:
        return is_good_date(self.date_rating)


def summarize(db: Connection, user_id: int, cards: Sequence[Row]) -> list[Card]:
    """The user's card rows, selected with `_COLUMNS`, with their card summaries, in the same order."""
    params = {"user_id": user_id, "ids": [card.id for card in cards]}
    last_messages = {
        row.card_id: dict(row._mapping)
        for row in db.execute(
            text(
                """
                SELECT DISTINCT ON (card_id) card_id, sender, left(body, 100) AS body, sent_at FROM messages
                WHERE user_id = :user_id AND card_id = ANY(:ids)
                ORDER BY card_id, sent_at DESC, id DESC
                """
            ),
            params,
        )
    }
    waiting = db.execute(
        text(
            f"""
            SELECT {_DRAFT_COLUMNS} FROM drafts
            WHERE user_id = :user_id AND card_id = ANY(:ids) AND status IN ('pending', 'copied', 'failed')
            ORDER BY created_at DESC, id DESC
            """
        ),
        params,
    ).all()
    drafts: dict[int, list[Draft]] = {}
    for draft in present(db, user_id, waiting):
        drafts.setdefault(draft.card_id, []).append(draft)
    lead_photos = dict(
        db.execute(
            text(
                "SELECT DISTINCT ON (card_id) card_id, url FROM card_photos"
                " WHERE user_id = :user_id AND card_id = ANY(:ids) ORDER BY card_id, id"
            ),
            params,
        ).all()
    )
    # shortcut: one hot-lead query per card, like the review queue. Fold `is_hot_lead()` into one query over
    # all the ids if a Pipeline of a few hundred cards gets slow.
    summaries = [
        {
            **card._mapping,
            "last_message": last_messages.get(card.id),
            "hot": is_hot_lead(db, user_id, card.id),
            "pending_draft": next((draft for draft in drafts.get(card.id, []) if draft.status == "pending"), None),
            "drafts": drafts.get(card.id, []),
            "lead_photo_url": lead_photos.get(card.id),
        }
        for card in cards
    ]
    from app.pipeline import place  # imported here: app.pipeline imports this module for `GET /pipeline`

    place(db, user_id, summaries)
    return [Card.model_validate(summary) for summary in summaries]


class NewCard(BaseModel):
    app: str
    name: str
    external_id: str | None = None
    stage: Stage = "matched"
    notes: str = ""
    next_action: str | None = None
    due_date: date | None = None


@router.post("/cards", status_code=201, response_model=Card)
def create_card(card: NewCard, user: CurrentUser, db: Db):
    if card.external_id and tombstones.is_buried(db, user.id, "match", card.app, card.external_id):
        raise HTTPException(status_code=409, detail="this person asked for their data to be deleted")
    try:
        row = db.execute(
            text(
                f"""
                INSERT INTO cards (user_id, app, external_id, name, stage, notes, next_action, due_date)
                VALUES (:user_id, :app, :external_id, :name, :stage, :notes, :next_action, :due_date)
                RETURNING {_COLUMNS}
                """
            ),
            {"user_id": user.id, **card.model_dump()},
        ).one()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="a card with this app and external_id already exists")
    return summarize(db, user.id, [row])[0]


def upsert_card(db: Connection, user_id: int, app: str, external_id: str, name: str) -> int | None:
    """Create the card for a synced match in Matched, or refresh its name. Returns the card id.

    An existing card keeps its stage, notes, next action and due date. A match the user purged is not stored
    again: None is returned and the caller must store nothing about them.
    """
    if tombstones.is_buried(db, user_id, "match", app, external_id):
        return None
    return db.execute(
        text(
            """
            INSERT INTO cards (user_id, app, external_id, name, stage)
            VALUES (:user_id, :app, :external_id, :name, 'matched')
            ON CONFLICT (user_id, app, external_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """
        ),
        {"user_id": user_id, "app": app, "external_id": external_id, "name": name},
    ).scalar_one()


def has_message(db: Connection, user_id: int, card_id: int, external_id: str) -> bool:
    return db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM messages"
            " WHERE card_id = :card_id AND user_id = :user_id AND external_id = :external_id)"
        ),
        {"card_id": card_id, "user_id": user_id, "external_id": external_id},
    ).scalar_one()


def _queue_reply(db: Connection, user_id: int, card_id: int) -> None:
    """Call after each new message from the match: chat autopilot answers it, if it may act (`app/chat_autopilot.py`)."""
    app = own_card(db, user_id, card_id).app
    if autopilot_allowed(db, user_id, app, "chat"):
        enqueue(db, user_id, "chat_reply", {"app": app, "card_id": card_id})


def upsert_message(
    db: Connection,
    user_id: int,
    card_id: int,
    external_id: str | None,
    sender: str,
    body: str,
    sent_at: datetime | str,
    *,
    sent_by_autopilot: bool = False,
) -> None:
    """Add a synced message unless the card already has it. Without an `external_id` it is always added.

    A new message has the same effects as one added through `POST /cards/{id}/messages`, and it also moves a
    Matched card to Chatting. `sent_by_autopilot` marks a message autopilot sent alone (`app/send.py`).
    """
    stored = insert_message(
        db, user_id, card_id, external_id, sender, body, sent_at, skip_duplicate=True, sent_by_autopilot=sent_by_autopilot
    )
    if stored:
        db.execute(
            text(
                "UPDATE cards SET stage = 'chatting', stage_changed_at = now()"
                " WHERE id = :card_id AND user_id = :user_id AND stage = 'matched'"
            ),
            {"card_id": card_id, "user_id": user_id},
        )


class CardChanges(BaseModel):
    name: str | None = None
    stage: Stage | None = None
    notes: str | None = None
    next_action: str | None = None
    due_date: date | None = None
    date_rating: int | None = Field(default=None, ge=1, le=5)
    date_note: str | None = None

    @field_validator("name", "stage", "notes")
    @classmethod
    def _not_null(cls, value):
        # None is only the "not sent" default; these columns cannot be cleared.
        if value is None:
            raise ValueError("cannot be null")
        return value


@router.get("/cards", response_model=list[Card])
def list_cards(user: CurrentUser, db: Db, stage: Stage | None = None, app: str | None = None):
    rows = db.execute(
        text(
            f"""
            SELECT {_COLUMNS} FROM cards
            WHERE user_id = :user_id
              AND (CAST(:stage AS text) IS NULL OR stage = :stage)
              AND (CAST(:app AS text) IS NULL OR app = :app)
            ORDER BY id
            """
        ),
        {"user_id": user.id, "stage": stage, "app": app},
    ).all()
    return summarize(db, user.id, rows)


@router.patch("/cards/{card_id}", response_model=Card)
def update_card(card_id: int, changes: CardChanges, user: CurrentUser, db: Db):
    """Change only the fields sent. Send `null` to clear `next_action` or `due_date`."""
    fields = changes.model_dump(exclude_unset=True)
    # Column names come from the model's own field names, never from the request.
    assignments = [f"{column} = :{column}" for column in fields]
    if "stage" in fields:
        # The right-hand side sees the old row, so the time moves only when the stage does.
        assignments.append("stage_changed_at = CASE WHEN stage <> :stage THEN now() ELSE stage_changed_at END")
        # Archiving, or any move out of the stallable stages, ends Stalled.
        assignments.append(f"stalled_at = CASE WHEN :stage IN {_STALLABLE} THEN stalled_at END")
    if fields.get("date_rating") is not None:
        # The first rating fixes the week the date counts in on the dashboard.
        assignments.append("date_rated_at = COALESCE(date_rated_at, now())")
    row = db.execute(
        text(
            f"""
            UPDATE cards SET {", ".join(assignments) or "notes = notes"}
            WHERE id = :id AND user_id = :user_id
            RETURNING {_COLUMNS}
            """
        ),
        {"id": card_id, "user_id": user.id, **fields},
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="card not found")
    if "stage" in fields:
        try:
            # Date set confirms the card's calendar hold; Archived releases its holds.
            calendar.stage_changed(db, user.id, card_id, fields["stage"])
        except httpx.HTTPError:
            # Raising rolls the stage change back, so the card and the calendar stay in step.
            raise HTTPException(status_code=502, detail="Google Calendar could not be reached; try again")
    return summarize(db, user.id, [row])[0]


@router.get("/cards/{card_id}", response_model=Card)
def read_card(card_id: int, user: CurrentUser, db: Db):
    return summarize(db, user.id, [own_card(db, user.id, card_id, _COLUMNS)])[0]


_MESSAGE_COLUMNS = "id, card_id, external_id, sender, body, sent_at, handover, sent_by_autopilot"


class Message(BaseModel):
    id: int
    card_id: int
    external_id: str | None
    sender: str
    body: str
    sent_at: datetime
    # The handover checks an incoming message hit (see `app/jev.py`); null when it was not checked.
    handover: list[str] | None
    # Autopilot sent it alone; false for the user's own messages, including drafts they sent.
    sent_by_autopilot: bool


class NewMessage(BaseModel):
    sender: Literal["me", "them"]
    body: str
    sent_at: datetime | None = None  # defaults to now
    external_id: str | None = None


def insert_message(
    db: Connection,
    user_id: int,
    card_id: int,
    external_id: str | None,
    sender: str,
    body: str,
    sent_at: datetime | str | None = None,
    *,
    skip_duplicate: bool = False,
    sent_by_autopilot: bool = False,
) -> dict | None:
    """Store one message on the user's card and run everything a new message sets off. Every message is
    stored through this function, so those effects are in one place:

    - from `me`: the style profile is rewritten from the user's own messages, a pending handover ends, and the
      card's copied drafts older than the message are `sent`;
    - from `them`: Stalled is cleared, the handover trigger runs, and chat autopilot is asked to reply.

    Returns the stored message, or None when the user has no such card. `sent_at` defaults to now. A message
    whose `external_id` the card already has raises `IntegrityError`; with `skip_duplicate` it is left alone
    and None is returned. `sent_by_autopilot` marks a message autopilot sent alone.
    """
    # Selecting from the user's cards means a card they do not own inserts nothing.
    row = db.execute(
        text(
            f"""
            INSERT INTO messages (user_id, card_id, external_id, sender, body, sent_at, sent_by_autopilot)
            SELECT user_id, id, :external_id, :sender, :body, COALESCE(CAST(:sent_at AS timestamptz), now()),
                :sent_by_autopilot
            FROM cards WHERE id = :card_id AND user_id = :user_id
            {"ON CONFLICT (card_id, external_id) DO NOTHING" if skip_duplicate else ""}
            RETURNING {_MESSAGE_COLUMNS}
            """
        ),
        {
            "card_id": card_id,
            "user_id": user_id,
            "external_id": external_id,
            "sender": sender,
            "body": body,
            "sent_at": sent_at,
            "sent_by_autopilot": sent_by_autopilot,
        },
    ).one_or_none()
    if not row:
        return None
    if sender == "me":
        queue_profile(db, user_id)
        handover.answered(db, user_id, card_id)
        # The user pasted what they copied: a copied draft older than this message is sent (ADR 0003).
        db.execute(
            text(
                "UPDATE drafts SET status = 'sent', updated_at = now()"
                " WHERE card_id = :card_id AND user_id = :user_id AND status = 'copied' AND copied_at < :sent_at"
            ),
            {"card_id": card_id, "user_id": user_id, "sent_at": row.sent_at},
        )
        return dict(row._mapping)
    # A reply clears Stalled. If it was an old message added late, the next `mark_stalled` run sets the flag again.
    db.execute(
        text("UPDATE cards SET stalled_at = NULL WHERE id = :id AND user_id = :user_id"),
        {"id": card_id, "user_id": user_id},
    )
    # shortcut: Jev is called here, inside the request or the sync job, once per sentence and check. Move
    # it to its own job if a sync gets slow.
    hits = handover.incoming(db, user_id, card_id, row.id, body)
    _queue_reply(db, user_id, card_id)
    return {**row._mapping, "handover": hits}


@router.post("/cards/{card_id}/messages", status_code=201, response_model=Message)
def add_message(card_id: int, message: NewMessage, user: CurrentUser, db: Db):
    try:
        stored = insert_message(
            db, user.id, card_id, message.external_id, message.sender, message.body, message.sent_at
        )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="a message with this external_id already exists on the card")
    if not stored:
        raise HTTPException(status_code=404, detail="card not found")
    return stored


@router.get("/cards/{card_id}/messages", response_model=list[Message])
def list_messages(card_id: int, user: CurrentUser, db: Db):
    own_card(db, user.id, card_id)  # 404 unless the card is the caller's
    return db.execute(
        text(
            f"""
            SELECT {_MESSAGE_COLUMNS} FROM messages
            WHERE card_id = :card_id AND user_id = :user_id
            ORDER BY sent_at, id
            """
        ),
        {"card_id": card_id, "user_id": user.id},
    ).all()
