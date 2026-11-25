"""Reads of one card that many modules share: the card itself, checked to be the user's, and its messages.

It imports no other feature module, so any of them can use it.
"""

from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import Connection, Row, text


def find_card(db: Connection, user_id: int, card_id: int, columns: str = "app, name, notes") -> Row | None:
    """The user's card, or None if they have no such card. `columns` is SQL from the caller's own code."""
    return db.execute(
        text(f"SELECT {columns} FROM cards WHERE id = :id AND user_id = :user_id"), {"id": card_id, "user_id": user_id}
    ).one_or_none()


def own_card(db: Connection, user_id: int, card_id: int, columns: str = "app, name, notes") -> Row:
    """The user's card, for a route: `404` if they have no such card."""
    card = find_card(db, user_id, card_id, columns)
    if not card:
        raise HTTPException(status_code=404, detail="card not found")
    return card


def conversation(db: Connection, user_id: int, card_id: int) -> list[Row]:
    """The card's messages as `(sender, body)`, oldest first."""
    return db.execute(
        text(
            "SELECT sender, body FROM messages WHERE card_id = :card_id AND user_id = :user_id ORDER BY sent_at, id"
        ),
        {"card_id": card_id, "user_id": user_id},
    ).all()


def chat_lines(messages: Iterable) -> list[str]:
    """Prompt lines for `(sender, body)` pairs; the sender is `me` or `them`."""
    return [f"{sender}: {body}" for sender, body in messages]


def unanswered(db: Connection, user_id: int, card_id: int) -> list[Row]:
    """The match's messages since the user's last one, oldest first: `id`, `body`, `handover`."""
    return db.execute(
        text(
            """
            SELECT id, body, handover FROM messages
            WHERE card_id = :card_id AND user_id = :user_id AND sender = 'them'
              AND sent_at > coalesce((SELECT max(sent_at) FROM messages WHERE card_id = :card_id
                                      AND user_id = :user_id AND sender = 'me'), '-infinity')
            ORDER BY sent_at, id
            """
        ),
        {"card_id": card_id, "user_id": user_id},
    ).all()
