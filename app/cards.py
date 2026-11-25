"""Match cards: one card per match, moving through the pipeline stages."""

from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, computed_field, field_validator
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.auth import CurrentUser, Db
from app.voice import queue_profile
from app.jobs import handler

router = APIRouter()

# The seven pipeline stages, in order. The `cards.stage` check constraint lists the same values.
Stage = Literal["matched", "chatting", "number_swapped", "date_set", "dated", "seeing_them", "archived"]

_COLUMNS = (
    "id, app, external_id, name, stage, stage_changed_at, notes, next_action, due_date, created_at,"
    " stalled_at IS NOT NULL AS stalled"
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

    @computed_field
    @property
    def suggested_actions(self) -> list[str]:
        """What the app offers on a Stalled card. `archive` is `PATCH /cards/{id}` with `stage: archived`."""
        return ["revive", "archive"] if self.stalled else []


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


class CardChanges(BaseModel):
    name: str | None = None
    stage: Stage | None = None
    notes: str | None = None
    next_action: str | None = None
    due_date: date | None = None

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


_MESSAGE_COLUMNS = "id, card_id, external_id, sender, body, sent_at"


class Message(BaseModel):
    id: int
    card_id: int
    external_id: str | None
    sender: str
    body: str
    sent_at: datetime


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
    if message.sender == "them":
        # A reply clears Stalled. If it was an old message added late, the next `mark_stalled` run sets the flag again.
        db.execute(
            text("UPDATE cards SET stalled_at = NULL WHERE id = :id AND user_id = :user_id"),
            {"id": card_id, "user_id": user.id},
        )
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
