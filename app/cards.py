"""Match cards: one card per match, moving through the pipeline stages."""

from datetime import date, datetime, timedelta
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, computed_field, field_validator
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app import calendar
from app import handover
from app.auth import CurrentUser, Db
from app.voice import queue_profile
from app.autopilot import autopilot_allowed
from app.jobs import enqueue, handler

router = APIRouter()

# The seven pipeline stages, in order. The `cards.stage` check constraint lists the same values.
Stage = Literal["matched", "chatting", "number_swapped", "date_set", "dated", "seeing_them", "archived"]

_COLUMNS = (
    "id, app, external_id, name, stage, stage_changed_at, notes, next_action, due_date, created_at,"
    " stalled_at IS NOT NULL AS stalled, date_rating, date_note, handover, handover_suggestions,"
    " led_to_date"
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


class Card(BaseModel):
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

    @computed_field
    @property
    def suggested_actions(self) -> list[str]:
        """What the app offers on a Stalled card. `archive` is `PATCH /cards/{id}` with `stage: archived`."""
        return ["revive", "archive"] if self.stalled else []

    @computed_field
    @property
    def good_date(self) -> bool:
        return is_good_date(self.date_rating)


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
    try:
        return db.execute(
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


def upsert_card(db: Connection, user_id: int, app: str, external_id: str, name: str) -> int:
    """Create the card for a synced match in Matched, or refresh its name. Returns the card id.

    An existing card keeps its stage, notes, next action and due date.
    """
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


def has_message(db: Connection, card_id: int, external_id: str) -> bool:
    return db.execute(
        text("SELECT EXISTS (SELECT 1 FROM messages WHERE card_id = :card_id AND external_id = :external_id)"),
        {"card_id": card_id, "external_id": external_id},
    ).scalar_one()


def _queue_reply(db: Connection, user_id: int, card_id: int) -> None:
    """Call after each new message from the match: chat autopilot answers it, if it may act (`app/chat_autopilot.py`)."""
    app = db.execute(text("SELECT app FROM cards WHERE id = :id"), {"id": card_id}).scalar_one()
    if autopilot_allowed(db, user_id, app, "chat"):
        enqueue(db, user_id, "chat_reply", {"app": app, "card_id": card_id})


def upsert_message(
    db: Connection, user_id: int, card_id: int, external_id: str | None, sender: str, body: str, sent_at: datetime | str
) -> None:
    """Add a synced message unless the card already has it. Without an `external_id` it is always added.

    A new message has the same effects as one added through `POST /cards/{id}/messages`, and it also moves a
    Matched card to Chatting.
    """
    added = db.execute(
        text(
            """
            INSERT INTO messages (user_id, card_id, external_id, sender, body, sent_at)
            VALUES (:user_id, :card_id, :external_id, :sender, :body, CAST(:sent_at AS timestamptz))
            ON CONFLICT (card_id, external_id) DO NOTHING
            RETURNING id
            """
        ),
        {
            "user_id": user_id,
            "card_id": card_id,
            "external_id": external_id,
            "sender": sender,
            "body": body,
            "sent_at": sent_at,
        },
    ).one_or_none()
    if not added:
        return
    db.execute(
        text(
            "UPDATE cards SET stage = 'chatting', stage_changed_at = now()"
            " WHERE id = :card_id AND user_id = :user_id AND stage = 'matched'"
        ),
        {"card_id": card_id, "user_id": user_id},
    )
    if sender == "me":
        queue_profile(db, user_id)
        handover.answered(db, card_id)
    else:
        # A reply clears Stalled, as in `add_message`.
        db.execute(
            text("UPDATE cards SET stalled_at = NULL WHERE id = :card_id AND user_id = :user_id"),
            {"card_id": card_id, "user_id": user_id},
        )
        # shortcut: Jev is called inside the sync job, once per sentence and check, also for old messages
        # on a first sync. Move to its own job if a sync gets slow.
        handover.incoming(db, user_id, card_id, added.id, body)
        _queue_reply(db, user_id, card_id)


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
    return db.execute(
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
    return row


@router.get("/cards/{card_id}", response_model=Card)
def read_card(card_id: int, user: CurrentUser, db: Db):
    row = db.execute(
        text(f"SELECT {_COLUMNS} FROM cards WHERE id = :id AND user_id = :user_id"),
        {"id": card_id, "user_id": user.id},
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="card not found")
    return row


_MESSAGE_COLUMNS = "id, card_id, external_id, sender, body, sent_at, handover"


class Message(BaseModel):
    id: int
    card_id: int
    external_id: str | None
    sender: str
    body: str
    sent_at: datetime
    # The handover checks an incoming message hit (see `app/jev.py`); null when it was not checked.
    handover: list[str] | None


class NewMessage(BaseModel):
    sender: Literal["me", "them"]
    body: str
    sent_at: datetime | None = None  # defaults to now
    external_id: str | None = None


@router.post("/cards/{card_id}/messages", status_code=201, response_model=Message)
def add_message(card_id: int, message: NewMessage, user: CurrentUser, db: Db):
    try:
        # Selecting from the caller's cards means a card they do not own inserts nothing.
        row = db.execute(
            text(
                f"""
                INSERT INTO messages (user_id, card_id, external_id, sender, body, sent_at)
                SELECT user_id, id, :external_id, :sender, :body, COALESCE(CAST(:sent_at AS timestamptz), now())
                FROM cards WHERE id = :card_id AND user_id = :user_id
                RETURNING {_MESSAGE_COLUMNS}
                """
            ),
            {"card_id": card_id, "user_id": user.id, **message.model_dump()},
        ).one_or_none()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="a message with this external_id already exists on the card")
    if not row:
        raise HTTPException(status_code=404, detail="card not found")
    if message.sender == "me":
        queue_profile(db, user.id)  # the style profile is written from the user's own messages
        handover.answered(db, card_id)
    if message.sender == "them":
        # A reply clears Stalled. If it was an old message added late, the next `mark_stalled` run sets the flag again.
        db.execute(
            text("UPDATE cards SET stalled_at = NULL WHERE id = :id AND user_id = :user_id"),
            {"id": card_id, "user_id": user.id},
        )
        hits = handover.incoming(db, user.id, card_id, row.id, message.body)
        _queue_reply(db, user.id, card_id)
        return {**row._mapping, "handover": hits}
    return row


@router.get("/cards/{card_id}/messages", response_model=list[Message])
def list_messages(card_id: int, user: CurrentUser, db: Db):
    read_card(card_id, user, db)  # 404 unless the card is the caller's
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
