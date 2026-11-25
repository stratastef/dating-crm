"""Voice: the user's questionnaire answers and the style profile that drafts are written from."""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import llm
from app.auth import CurrentUser, Db
from app.jobs import enqueue, handler

router = APIRouter()


class Questionnaire(BaseModel):
    answers: dict[str, str]  # question -> answer


class Voice(BaseModel):
    answers: dict[str, str]
    profile: str | None  # null until the worker has generated it


@router.put("/voice/questionnaire", response_model=Voice)
def save_questionnaire(questionnaire: Questionnaire, user: CurrentUser, db: Db):
    """Replace the user's questionnaire answers and queue a rewrite of the style profile."""
    queue_profile(db, user.id)
    return db.execute(
        text(
            """
            INSERT INTO voice_profiles (user_id, answers) VALUES (:user_id, CAST(:answers AS jsonb))
            ON CONFLICT (user_id) DO UPDATE SET answers = EXCLUDED.answers, updated_at = now()
            RETURNING answers, profile
            """
        ),
        {"user_id": user.id, "answers": json.dumps(questionnaire.answers)},
    ).one()


@router.get("/voice", response_model=Voice)
def read_voice(user: CurrentUser, db: Db):
    row = db.execute(
        text("SELECT answers, profile FROM voice_profiles WHERE user_id = :user_id"), {"user_id": user.id}
    ).one_or_none()
    return row or Voice(answers={}, profile=None)


class ChatMessage(BaseModel):
    sender: str
    body: str


class PastChat(BaseModel):
    card_id: int
    similarity: float  # 0 to 1
    messages: list[ChatMessage]


def similar_chats(db: Connection, user_id: int, card_id: int, limit: int = 3) -> list:
    """The user's past chats that led to a date, most similar to the card's conversation first."""
    # shortcut: trigram similarity of the whole chat text, computed per query with no index. Move to
    # embeddings (pgvector) if drafts need likeness of meaning rather than of wording.
    # shortcut: a chat counts as "led to a date" by its current stage, so a dated card that was later
    # archived is missed until stage history exists.
    return db.execute(
        text(
            """
            WITH chats AS (
                SELECT c.id AS card_id,
                       string_agg(m.body, E'\n' ORDER BY m.sent_at, m.id) AS body,
                       json_agg(json_build_object('sender', m.sender, 'body', m.body) ORDER BY m.sent_at, m.id)
                           AS messages
                FROM cards c JOIN messages m ON m.card_id = c.id
                WHERE c.user_id = :user_id
                  AND (c.id = :card_id OR c.stage IN ('date_set', 'dated', 'seeing_them'))
                GROUP BY c.id
            )
            SELECT past.card_id, similarity(past.body, coalesce(given.body, '')) AS similarity, past.messages
            FROM chats past LEFT JOIN chats given ON given.card_id = :card_id
            WHERE past.card_id <> :card_id
            ORDER BY similarity DESC, past.card_id DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "card_id": card_id, "limit": limit},
    ).all()


@router.get("/cards/{card_id}/similar-chats", response_model=list[PastChat])
def read_similar_chats(card_id: int, user: CurrentUser, db: Db, limit: int = Query(3, ge=1, le=20)):
    owned = db.execute(
        text("SELECT 1 FROM cards WHERE id = :id AND user_id = :user_id"), {"id": card_id, "user_id": user.id}
    ).first()
    if not owned:
        raise HTTPException(status_code=404, detail="card not found")
    return similar_chats(db, user.id, card_id, limit)


def queue_profile(db: Connection, user_id: int) -> None:
    """Queue a rewrite of the user's style profile. Call it whenever a message of theirs is stored."""
    # One waiting job is enough: it reads everything stored by the time it runs.
    # shortcut: a message stored while that job is already running is picked up only by the next rewrite.
    waiting = db.execute(
        text("SELECT 1 FROM jobs WHERE user_id = :user_id AND kind = 'voice_profile' AND status = 'queued'"),
        {"user_id": user_id},
    ).first()
    if not waiting:
        enqueue(db, user_id, "voice_profile")


_SYSTEM = (
    "You write a style profile of how one person texts on dating apps. A later step drafts messages in their"
    " voice from this profile alone. Describe tone, humour, message length, punctuation, capitalisation, emoji"
    " use, typical openers and how they ask someone out. Use only what the answers and messages show. Reply"
    " with the profile only, under 300 words."
)

# shortcut: only the newest messages are read, summarise in batches if older chats turn out to matter.
_MESSAGE_LIMIT = 200


@handler("voice_profile")
def write_profile(db: Connection, user_id: int, payload: dict) -> None:
    """Write the style profile from the questionnaire answers and the user's own stored messages."""
    answers = db.execute(
        text("SELECT answers FROM voice_profiles WHERE user_id = :user_id"), {"user_id": user_id}
    ).scalar_one_or_none()
    messages = db.execute(
        text(
            "SELECT body FROM messages WHERE user_id = :user_id AND sender = 'me'"
            " ORDER BY sent_at DESC, id DESC LIMIT :limit"
        ),
        {"user_id": user_id, "limit": _MESSAGE_LIMIT},
    ).scalars()
    prompt = "\n".join(
        [
            "<questionnaire>",
            *(f"Q: {question}\nA: {answer}" for question, answer in (answers or {}).items()),
            "</questionnaire>",
            "<my_messages>",
            *reversed(list(messages)),
            "</my_messages>",
        ]
    )
    profile = llm.call(db, user_id, "voice_profile", _SYSTEM, prompt).text
    db.execute(
        text(
            """
            INSERT INTO voice_profiles (user_id, profile) VALUES (:user_id, :profile)
            ON CONFLICT (user_id) DO UPDATE SET profile = EXCLUDED.profile, updated_at = now()
            """
        ),
        {"user_id": user_id, "profile": profile},
    )
