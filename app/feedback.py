"""Feedback loop: what the user did before goes into later prompts, and the labelled data can be exported.

Nothing is trained in v1. The loop changes prompts and retrieval only: `similar_chats()` ranks good dates
first and the style profile reads draft edits (both in `app/voice.py`); the swipe pre-screen reads
`swipe_lines()`.
"""

import json

from fastapi import APIRouter, Response
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db
from app.cards import is_good_date

router = APIRouter()

# shortcut: only the newest few of each signal go into the pre-screen prompt; summarise them into the
# preferences if older ones turn out to matter.
_LIMIT = 10


def _one_line(value: str) -> str:
    return " ".join(value.split())


def swipe_lines(db: Connection, user_id: int) -> list[str]:
    """Prompt lines for the swipe pre-screen: the user's manual swipes against the screen, and their rated dates."""
    # An unattended swipe is the screen's own choice, and a swipe that agrees with the screen adds nothing.
    overrides = db.execute(
        text(
            "SELECT suggestion, decision, bio FROM swipe_candidates WHERE user_id = :user_id AND NOT unattended"
            " AND decision <> suggestion AND bio <> '' ORDER BY decided_at DESC, id DESC LIMIT :limit"
        ),
        {"user_id": user_id, "limit": _LIMIT},
    ).all()
    # A rated date is described by the user's own notes about the match and about the date.
    dates = db.execute(
        text(
            "SELECT date_rating, concat_ws('. ', nullif(notes, ''), nullif(date_note, '')) AS about FROM cards"
            " WHERE user_id = :user_id AND date_rating IS NOT NULL"
            " AND concat(notes, date_note) <> '' ORDER BY date_rated_at DESC, id DESC LIMIT :limit"
        ),
        {"user_id": user_id, "limit": _LIMIT},
    ).all()
    return [
        "<manual_swipes>",
        *(f"screen said {row.suggestion}, user chose {row.decision}: {_one_line(row.bio)}" for row in overrides),
        "</manual_swipes>",
        "<rated_dates>",
        *(f"rated {row.date_rating} of 5: {_one_line(row.about)}" for row in dates),
        "</rated_dates>",
    ]


@router.get("/feedback/export")
def export(user: CurrentUser, db: Db) -> Response:
    """The caller's labelled data as JSON Lines, one example per line: the dataset for later fine-tuning.

    Read from the live tables at each request and stored nowhere else, so a purged person is not in it.
    Names and IDs are left out; the texts are the user's own data.
    """
    # shortcut: the whole export is built in memory. Stream it if a user's data gets large.
    params = {"user_id": user.id}
    chats = db.execute(
        text(
            """
            SELECT c.app, c.led_to_date, c.date_rating,
                   json_agg(json_build_object('sender', m.sender, 'body', m.body) ORDER BY m.sent_at, m.id) AS messages
            FROM cards c JOIN messages m ON m.card_id = c.id
            WHERE c.user_id = :user_id GROUP BY c.id ORDER BY c.id
            """
        ),
        params,
    ).all()
    edits = db.execute(
        text("SELECT kind, original, edited FROM drafts WHERE user_id = :user_id AND edited <> original ORDER BY id"),
        params,
    ).all()
    swipes = db.execute(
        text(
            "SELECT app, bio, suggestion, decision FROM swipe_candidates"
            " WHERE user_id = :user_id AND decision IS NOT NULL AND NOT unattended ORDER BY id"
        ),
        params,
    ).all()
    examples = [
        *(
            {
                "type": "chat",
                "app": chat.app,
                "led_to_date": chat.led_to_date,
                "date_rating": chat.date_rating,
                "good_date": is_good_date(chat.date_rating),
                "messages": chat.messages,
            }
            for chat in chats
        ),
        *({"type": "draft_edit", **edit._mapping} for edit in edits),
        *({"type": "swipe", **swipe._mapping} for swipe in swipes),
    ]
    return Response(
        "".join(json.dumps(example, ensure_ascii=False) + "\n" for example in examples),
        media_type="application/x-ndjson",
    )
