"""Sending a draft through a connector: `queue_send()` approves a draft and the `send_draft` job sends it once."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import Connection, Row, text

from app.audit import record_action
from app.auth import CurrentUser, Db
from app.autopilot import pauses
from app.cards import upsert_message
from app.connectors import CapabilityFailed, call, unavailable
from app.drafts import _COLUMNS, Draft
from app.jobs import enqueue, handler
from app.sync import CONNECTORS

router = APIRouter()


def queue_send(db: Connection, user_id: int, draft_id: int, trigger: str) -> Row | None:
    """Approve a pending draft and queue the job that sends it, in the caller's transaction.

    Returns the draft, now `approved`, or None if the user has no such draft or it is not `pending`, so a
    draft is queued at most once. `trigger` is what caused the send; it goes to the audit log.
    """
    draft = db.execute(
        text(
            f"""
            UPDATE drafts SET status = 'approved', updated_at = now()
            WHERE id = :id AND user_id = :user_id AND status = 'pending' RETURNING {_COLUMNS}
            """
        ),
        {"id": draft_id, "user_id": user_id},
    ).one_or_none()
    if draft:
        enqueue(db, user_id, "send_draft", {"draft_id": draft_id, "trigger": trigger})
    return draft


def refusal(db: Connection, user_id: int, app: str, match_id: str | None) -> str | None:
    """Why a message cannot be sent to this match now, or None if it can. The kill switch stops tapped sends too."""
    if app not in CONNECTORS:
        return f"{app} has no connector"
    if not match_id:
        return f"the card is not linked to a {app} match"
    paused = pauses(db, user_id)
    if paused["all"] or app in paused["apps"]:
        return f"{app} is paused"
    return unavailable(db, user_id, CONNECTORS[app](), "send")


@router.post("/drafts/{draft_id}/send", response_model=Draft, status_code=202)
def tap_send(draft_id: int, user: CurrentUser, db: Db):
    """The user approves a draft: queue it for the worker to send. `409` says why when it cannot be sent."""
    card = db.execute(
        text(
            "SELECT c.app, c.external_id, d.status FROM drafts d JOIN cards c ON c.id = d.card_id"
            " WHERE d.id = :id AND d.user_id = :user_id"
        ),
        {"id": draft_id, "user_id": user.id},
    ).one_or_none()
    if not card:
        raise HTTPException(status_code=404, detail="draft not found")
    why = refusal(db, user.id, card.app, card.external_id)
    if why:
        raise HTTPException(status_code=409, detail=why)
    draft = queue_send(db, user.id, draft_id, trigger=f"copilot: user tapped send on draft {draft_id}")
    if not draft:
        raise HTTPException(status_code=409, detail=f"the draft is already {card.status}")
    return draft


@handler("send_draft")
def send_draft(db: Connection, user_id: int, payload: dict) -> None:
    """Send an approved draft, at most once, and store the sent message on its card. Safe to run twice."""
    draft_id = payload["draft_id"]
    # The claim commits on its own before the app is touched, so it survives a crash or a failed attempt.
    # A run that finds the draft already `sending` follows an attempt that died: the message may have gone
    # out, so it is not sent again.
    with db.engine.begin() as own:
        claimed = own.execute(
            text(
                """
                UPDATE drafts SET status = CASE status WHEN 'approved' THEN 'sending' ELSE 'failed' END,
                    updated_at = now()
                WHERE id = :id AND user_id = :user_id AND status IN ('approved', 'sending') RETURNING status
                """
            ),
            {"id": draft_id, "user_id": user_id},
        ).scalar_one_or_none()
    if claimed != "sending":
        return
    draft = db.execute(
        text(
            "SELECT coalesce(d.edited, d.original) AS body, c.id AS card_id, c.app, c.external_id"
            " FROM drafts d JOIN cards c ON c.id = d.card_id WHERE d.id = :id"
        ),
        {"id": draft_id},
    ).one()

    def finish(status: str) -> None:
        db.execute(
            text("UPDATE drafts SET status = :status, updated_at = now() WHERE id = :id"),
            {"id": draft_id, "status": status},
        )

    if refusal(db, user_id, draft.app, draft.external_id):
        return finish("pending")  # nothing was sent: the user can tap again once the cause is fixed
    try:
        sent = call(db, user_id, CONNECTORS[draft.app](), "send", draft.external_id, draft.body)
    except CapabilityFailed:
        return finish("failed")  # no retry: the message may have reached the app before the error
    upsert_message(db, user_id, draft.card_id, sent["id"], "me", draft.body, sent["sent_at"])
    record_action(
        db, user_id, type="message", app=draft.app, target=f"card:{draft.card_id}", trigger=payload["trigger"]
    )
    finish("sent")
