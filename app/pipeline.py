"""The Pipeline: every card grouped by who acts next (ADR 0007).

`place()` decides each card's Pipeline group, the reason it waits for the user and what autopilot is doing on
it. `summarize()` in `app/cards.py` calls it, so every card summary carries them. `GET /pipeline` lists the groups.
"""

from datetime import date, datetime
from typing import Literal, get_args

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db
from app.autopilot import autopilot_block
from app.cards import _COLUMNS, Card, summarize
from app.send import CHAT_STAGES, refusal
from app.settings import user_zone

router = APIRouter()

# The groups, in the order the Pipeline lists them. An Archived card is Archived, as in the prototype: archiving
# is how the user is done with it. Any other card gets the first group that matches.
Group = Literal["waiting_for_you", "handled_by_autopilot", "waiting_for_them", "texting_off_app", "archived"]

# Why a card is Waiting for you, in precedence order: the first that applies is the card's `reason`.
Reason = Literal[
    "handover", "draft_in_review", "copied_draft", "failed_send", "stalled", "overdue", "rate_date",
    "your_turn", "opener_due",
]

# What autopilot is doing on a card Handled by autopilot. The time is the last message's `sent_at`, or for
# `planned` the planned send's `send_at`, an opener's too. `writing_opener` has no time: the job sets it.
Activity = Literal["writing_opener", "drafting_reply", "planned", "sent_waiting"]


def place(db: Connection, user_id: int, cards: list[dict]) -> None:
    """Add `pipeline_group`, `reason`, `autopilot_activity` and `handover_trigger` to each card summary.

    `cards` are rows selected with `_COLUMNS` of `app/cards.py`, with `last_message`, `pending_draft` and
    `planned_send` added.
    """
    params = {"user_id": user_id, "ids": [card["id"] for card in cards]}
    # The statuses of the card's drafts that wait for the user besides a pending one.
    drafts: dict[int, set[str]] = {}
    for card_id, status in db.execute(
        text(
            "SELECT card_id, status FROM drafts"
            " WHERE user_id = :user_id AND card_id = ANY(:ids) AND status IN ('copied', 'failed')"
        ),
        params,
    ):
        drafts.setdefault(card_id, set()).add(status)
    # A job that is running is still `queued` until it ends (see `app/jobs.py`).
    replying = set(
        db.execute(
            text(
                "SELECT CAST(payload->>'card_id' AS int) FROM jobs"
                " WHERE user_id = :user_id AND kind = 'chat_reply' AND status = 'queued'"
            ),
            params,
        ).scalars()
    )
    # The checks the newest flagged message from the match hit: what started the handover.
    triggers = dict(
        db.execute(
            text(
                """
                SELECT DISTINCT ON (card_id) card_id, handover[1] FROM messages
                WHERE user_id = :user_id AND card_id = ANY(:ids) AND sender = 'them' AND cardinality(handover) > 0
                ORDER BY card_id, sent_at DESC, id DESC
                """
            ),
            params,
        ).all()
    )
    today = datetime.now(user_zone(db, user_id)).date()  # the user's day, as on Today
    acting: dict[tuple[str, bool], bool] = {}  # (app, card linked to a match) -> chat autopilot may act now

    for card in cards:
        last = card["last_message"]
        handled = False
        # A handover, pending or taken over, keeps autopilot off the card.
        if card["stage"] in CHAT_STAGES and card["handover"] is None:
            key = (card["app"], card["external_id"] is not None)
            if key not in acting:
                # A pause, the AI budget, the autonomy level, then a working connector and a linked match: the
                # rules an unattended send is held to (`app/send.py`). The same answer for every card of the key.
                acting[key] = not autopilot_block(db, user_id, card["app"], "chat") and not refusal(
                    db, user_id, card["app"], card["external_id"]
                )
            # Autopilot acts on a chat only through a queued job: without one, the user acts next. `chat_reply`
            # answers the match, or writes the opener to a new match, then a planned send waits for its send time.
            handled = acting[key] and (
                card["id"] in replying or card["planned_send"] is not None or bool(last) and last["sender"] == "me"
            )

        reason = None if card["stage"] == "archived" else _reason(card, drafts.get(card["id"], set()), today, handled)
        card["reason"] = reason
        card["handover_trigger"] = triggers.get(card["id"]) if reason == "handover" else None
        card["autopilot_activity"] = None
        if card["stage"] == "archived":
            card["pipeline_group"] = "archived"
        elif reason:
            card["pipeline_group"] = "waiting_for_you"
        elif card["stage"] not in CHAT_STAGES:
            card["pipeline_group"] = "texting_off_app"
        elif handled:
            card["pipeline_group"] = "handled_by_autopilot"
            if card["planned_send"]:
                card["autopilot_activity"] = "planned"
            elif not last:
                card["autopilot_activity"] = "writing_opener"
            else:
                card["autopilot_activity"] = "drafting_reply" if last["sender"] == "them" else "sent_waiting"
        else:
            card["pipeline_group"] = "waiting_for_them"


def _reason(card: dict, drafts: set[str], today: date, handled: bool) -> Reason | None:
    """Why the card waits for the user, or None. The order of the checks is the precedence of `Reason`."""
    last = card["last_message"]
    if card["handover"] == "pending":
        return "handover"
    if card["pending_draft"]:
        return "draft_in_review"
    if "copied" in drafts:  # its message has not appeared in the chat yet
        return "copied_draft"
    if "failed" in drafts:
        return "failed_send"
    if card["stalled"]:
        return "stalled"
    # Due today is not overdue yet.
    if card["next_action"] and card["due_date"] and card["due_date"] < today:
        return "overdue"
    if card["stage"] == "dated" and card["date_rating"] is None:
        return "rate_date"
    if card["stage"] in CHAT_STAGES and not handled:
        if last and last["sender"] == "them" and not card["scheduled_send"]:  # a scheduled reply answers it
            return "your_turn"
        if card["stage"] == "matched" and not last:
            return "opener_due"
    return None


class PipelineGroup(BaseModel):
    group: str  # a `Group`
    cards: list[Card]


@router.get("/pipeline", response_model=list[PipelineGroup])
def read_pipeline(user: CurrentUser, db: Db):
    """Every card of the user, in its group. Groups in `Group` order, empty ones left out. Inside a group, hot
    leads first, then the most recent activity: the last message, or the last stage change without one."""
    rows = db.execute(text(f"SELECT {_COLUMNS} FROM cards WHERE user_id = :user_id ORDER BY id"), {"user_id": user.id}).all()
    cards = sorted(
        summarize(db, user.id, rows),
        key=lambda card: (
            not card.hot,
            -(card.last_message.sent_at if card.last_message else card.stage_changed_at).timestamp(),
        ),
    )
    groups = [(group, [card for card in cards if card.pipeline_group == group]) for group in get_args(Group)]
    return [{"group": group, "cards": members} for group, members in groups if members]
