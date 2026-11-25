"""Sending a draft through a connector: `queue_send()` approves a draft and the `send_draft` job sends it once."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import Connection, Row, text

from app.audit import record_action
from app.auth import CurrentUser, Db
from app import calendar, handover
from app.autopilot import autopilot_block
from app.cards import upsert_message
from app.connectors import CapabilityFailed, call, unavailable
from app.drafts import _COLUMNS, Draft
from app.jobs import enqueue, handler
from app.sync import CONNECTORS

router = APIRouter()


# The stages in which autopilot chats. From Number swapped on the user texts off the app.
CHAT_STAGES = ("matched", "chatting")


def unattended_block(db: Connection, user_id: int, draft_id: int) -> str | None:
    """Why this draft may not be sent without the user, or None if it may. Every rule for a message that
    goes out unattended is here; it is asked when the send is queued and again just before the app is called.
    """
    draft = db.execute(
        text(
            "SELECT d.guardrail, c.id AS card_id, c.app, c.stage FROM drafts d JOIN cards c ON c.id = d.card_id"
            " WHERE d.id = :id AND d.user_id = :user_id"
        ),
        {"id": draft_id, "user_id": user_id},
    ).one_or_none()
    if not draft:
        return "draft not found"
    block = autopilot_block(db, user_id, draft.app, "chat")  # the kill switch, the AI budget and the autonomy level
    if block:
        return block
    if draft.guardrail != []:  # a hit, Jev unavailable (`["unavailable"]`) or never checked (null)
        return f"the draft guardrail was hit: {draft.guardrail}"
    if handover.is_paused(db, user_id, draft.card_id):
        return "the card is paused for handover"
    if draft.stage not in CHAT_STAGES:
        return f"the card is in {draft.stage}"
    return None


def queue_send(db: Connection, user_id: int, draft_id: int, trigger: str, unattended: bool = False) -> Row | None:
    """Approve a pending draft and queue the job that sends it, in the caller's transaction.

    Returns the draft, now `approved`, or None if the user has no such draft or it is not `pending`, so a
    draft is queued at most once. `trigger` is what caused the send; it goes to the audit log.

    `unattended=True` is for a send no user asked for. It returns None and leaves the draft `pending`, so in
    the review queue, when `unattended_block()` gives a reason; the job asks again before it sends.
    """
    if unattended and unattended_block(db, user_id, draft_id):
        return None
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
        enqueue(db, user_id, "send_draft", {"draft_id": draft_id, "trigger": trigger, "unattended": unattended})
    return draft


def send_approved(db: Connection, user_id: int, draft_id: int, trigger: str) -> None:
    """Queue the send of a draft the caller has just moved to `approved`, if its card's app can send now.

    For the review queue, which approves drafts itself. Call it once per draft: a second job for the same
    draft would mark it `failed`. When the app cannot send, the draft stays `approved` and the user copies it.
    """
    card = _card(db, user_id, draft_id)
    if card and card.status == "approved" and not refusal(db, user_id, card.app, card.external_id, card.guardrail):
        enqueue(db, user_id, "send_draft", {"draft_id": draft_id, "trigger": trigger})


def _card(db: Connection, user_id: int, draft_id: int) -> Row | None:
    """The app and match a draft would be sent to, and the draft's status."""
    return db.execute(
        text(
            "SELECT c.app, c.external_id, d.status, d.guardrail FROM drafts d JOIN cards c ON c.id = d.card_id"
            " WHERE d.id = :id AND d.user_id = :user_id"
        ),
        {"id": draft_id, "user_id": user_id},
    ).one_or_none()


def refusal(
    db: Connection, user_id: int, app: str, match_id: str | None, guardrail: list[str] | None = None
) -> str | None:
    """Why a message cannot be sent to this match now, or None if it can. The kill switch is not asked: it
    pauses autopilot, and `unattended_block()` holds it for a send no user asked for. A tap still sends.

    `guardrail` is the draft's guardrail result. The user's tap may send a draft with any other hit, because
    they have read it; a draft that denies being AI is never sent, by a tap or alone, until it is edited.
    """
    if "denies_ai" in (guardrail or []):
        return "the draft denies being AI: edit it before sending"
    if app not in CONNECTORS:
        return f"{app} has no connector"
    if not match_id:
        return f"the card is not linked to a {app} match"
    return unavailable(db, user_id, CONNECTORS[app](), "send")


@router.post("/drafts/{draft_id}/send", response_model=Draft, status_code=202)
def tap_send(draft_id: int, user: CurrentUser, db: Db):
    """The user approves a draft: queue it for the worker to send. `409` says why when it cannot be sent."""
    card = _card(db, user.id, draft_id)
    if not card:
        raise HTTPException(status_code=404, detail="draft not found")
    why = refusal(db, user.id, card.app, card.external_id, card.guardrail)
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
    if claimed is None:
        return
    draft = db.execute(
        text(
            "SELECT coalesce(d.edited, d.original) AS body, d.guardrail, c.id AS card_id, c.app, c.external_id"
            " FROM drafts d JOIN cards c ON c.id = d.card_id WHERE d.id = :id AND d.user_id = :user_id"
        ),
        {"id": draft_id, "user_id": user_id},
    ).one()

    def finish(status: str) -> None:
        db.execute(
            text("UPDATE drafts SET status = :status, updated_at = now() WHERE id = :id AND user_id = :user_id"),
            {"id": draft_id, "user_id": user_id, "status": status},
        )
        if status == "failed":
            # The offer did not go out as far as the app knows, so the slots it named are free again.
            # shortcut: if the message did reach the match before the error, they hold an offer for a slot
            # that is no longer held. Keep the holds of a failed draft if that ever double-books.
            calendar.release_holds(
                db, user_id, draft.card_id, trigger=f"draft {draft_id} failed to send", draft_id=draft_id
            )

    if claimed == "failed":
        return finish("failed")  # an earlier attempt died: only its holds are left to release

    if refusal(db, user_id, draft.app, draft.external_id, draft.guardrail):
        return finish("pending")  # nothing was sent: the user can tap again once the cause is fixed
    if payload.get("unattended") and unattended_block(db, user_id, draft_id):
        return finish("pending")  # something changed since the send was queued: the draft waits for the user
    try:
        sent = call(db, user_id, CONNECTORS[draft.app](), "send", draft.external_id, draft.body)
    except CapabilityFailed:
        return finish("failed")  # no retry: the message may have reached the app before the error
    upsert_message(db, user_id, draft.card_id, sent["id"], "me", draft.body, sent["sent_at"])
    record_action(
        db, user_id, type="message", app=draft.app, target=f"card:{draft.card_id}", trigger=payload["trigger"]
    )
    finish("sent")
