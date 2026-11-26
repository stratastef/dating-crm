"""Sending a draft through a connector: `queue_send()` approves a draft and the `send_draft` job sends it once.
`cancel_send()` takes a queued send back until the job starts."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException
from sqlalchemy import Connection, Row, text

from app import calendar, handover
from app.audit import record_action
from app.auth import CurrentUser, Db
from app.autopilot import autopilot_block
from app.cards import upsert_message
from app.connectors import CapabilityFailed, call, unavailable
from app.drafts import _COLUMNS, Draft, present
from app.jobs import enqueue, handler
from app.sync import CONNECTORS

router = APIRouter()


# Chat autopilot adds this sentence to the first message it sends alone to a match while the user's AI
# disclosure is on (`app/chat_autopilot.py`). Sending a message that carries it sets `cards.ai_disclosed`.
DISCLOSURE = "Heads up: an AI assistant helps me write my messages here."

# The stages in which autopilot chats. From Number swapped on the user texts off the app.
CHAT_STAGES = ("matched", "chatting")

# How long a user's Send waits before the worker sends it, so the user can take it back (`undo_send`).
UNDO_WINDOW = timedelta(seconds=5)


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
    block = autopilot_block(db, user_id, draft.app, "chat")  # a pause, the AI budget and the autonomy level
    if block:
        return block
    if draft.guardrail != []:  # a hit, Jev unavailable (`["unavailable"]`) or never checked (null)
        return f"the draft guardrail was hit: {draft.guardrail}"
    if handover.is_paused(db, user_id, draft.card_id):
        return "the card is paused for handover"
    if draft.stage not in CHAT_STAGES:
        return f"the card is in {draft.stage}"
    return None


def queue_send(
    db: Connection,
    user_id: int,
    draft_id: int,
    trigger: str,
    unattended: bool = False,
    run_at: datetime | None = None,
) -> Row | None:
    """Approve a pending draft, or a failed one again (Retry), and queue the job that sends it, in the caller's
    transaction.

    Returns the draft, now `approved`, or None if the user has no such draft or it is not `pending` or `failed`,
    so a draft is queued at most once. `trigger` is what caused the send; it goes to the audit log.

    The job runs at `run_at`, or at once. Until it starts, `cancel_send()` takes the send back.

    `unattended=True` is for a send no user asked for. It returns None and leaves the draft `pending`, so in
    the review queue, when `unattended_block()` gives a reason; the job asks again before it sends.
    """
    if unattended and unattended_block(db, user_id, draft_id):
        return None
    draft = db.execute(
        text(
            f"""
            UPDATE drafts SET status = 'approved', updated_at = now()
            WHERE id = :id AND user_id = :user_id AND status IN ('pending', 'failed') RETURNING {_COLUMNS}
            """
        ),
        {"id": draft_id, "user_id": user_id},
    ).one_or_none()
    if draft:
        payload = {"draft_id": draft_id, "trigger": trigger, "unattended": unattended}
        enqueue(db, user_id, "send_draft", payload, run_at=run_at)
    return draft


def cancel_send(db: Connection, user_id: int, draft_id: int) -> Row | None:
    """Take back a queued send before its job starts, in the caller's transaction: the draft is `pending` again
    and its job does not run. Returns the draft, or None if it is not `approved`: the job has claimed it, or it
    was never queued."""
    draft = db.execute(
        text(
            f"""
            UPDATE drafts SET status = 'pending', updated_at = now()
            WHERE id = :id AND user_id = :user_id AND status = 'approved' RETURNING {_COLUMNS}
            """
        ),
        {"id": draft_id, "user_id": user_id},
    ).one_or_none()
    if draft:
        # Cancelled, not left to find the draft `pending`: a send queued again must not go out at the old time.
        # A job a worker holds is skipped, not waited for; it finds the draft `pending` and sends nothing.
        db.execute(
            text(
                """
                UPDATE jobs SET status = 'skipped', last_error = 'the send was taken back' WHERE id IN (
                    SELECT id FROM jobs WHERE user_id = :user_id AND kind = 'send_draft' AND status = 'queued'
                      AND (payload->>'draft_id')::int = :id
                    FOR UPDATE SKIP LOCKED)
                """
            ),
            {"id": draft_id, "user_id": user_id},
        )
    return draft


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
    """Why a message cannot be sent to this match now, or None if it can. A pause is not asked: it
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
    """The user's Send: queue the draft for the worker to send once `UNDO_WINDOW` has passed. `409` says why
    when it cannot be sent."""
    card = _card(db, user.id, draft_id)
    if not card:
        raise HTTPException(status_code=404, detail="draft not found")
    why = refusal(db, user.id, card.app, card.external_id, card.guardrail)
    if why:
        raise HTTPException(status_code=409, detail=why)
    trigger = f"copilot: user tapped send on draft {draft_id}"
    draft = queue_send(db, user.id, draft_id, trigger, run_at=datetime.now(UTC) + UNDO_WINDOW)
    if not draft:
        raise HTTPException(status_code=409, detail=f"the draft is already {card.status}")
    return present(db, user.id, [draft])[0]


@router.post("/drafts/{draft_id}/undo-send", response_model=Draft)
def undo_send(draft_id: int, user: CurrentUser, db: Db):
    """Take back the user's Send while its job has not started: the draft is `pending` again, its edit kept.
    `409` once the worker has started sending it."""
    card = _card(db, user.id, draft_id)
    if not card:
        raise HTTPException(status_code=404, detail="draft not found")
    draft = cancel_send(db, user.id, draft_id)
    if not draft:
        raise HTTPException(status_code=409, detail=f"the draft is {card.status}")
    return present(db, user.id, [draft])[0]


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
    upsert_message(
        db,
        user_id,
        draft.card_id,
        sent["id"],
        "me",
        draft.body,
        sent["sent_at"],
        sent_by_autopilot=bool(payload.get("unattended")),
    )
    if DISCLOSURE in draft.body:
        # Whoever sent it, the match has now been told: chat autopilot does not add the sentence again.
        db.execute(
            text("UPDATE cards SET ai_disclosed = true WHERE id = :id AND user_id = :user_id"),
            {"id": draft.card_id, "user_id": user_id},
        )
    record_action(
        db, user_id, type="message", app=draft.app, target=f"card:{draft.card_id}", trigger=payload["trigger"]
    )
    finish("sent")
