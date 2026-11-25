"""Read sync: the recurring `sync_matches` job copies each app's matches and messages into cards.
Submitting a session token also runs it at once."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db
from app.cards import has_message, upsert_card, upsert_message
from app.connectors import CapabilityUnavailable, Connector, call
from app.jobs import enqueue, handler
from app.tinder import TinderConnector
from app.vault import store_token

router = APIRouter()

# The apps that have a connector. Add each new connector here.
CONNECTORS: dict[str, type[Connector]] = {"tinder": TinderConnector}

SYNC_INTERVAL = timedelta(minutes=15)


class SessionToken(BaseModel):
    token: str = Field(min_length=1)


@router.put("/connectors/{app}/token", status_code=204)
def submit_token(app: str, session: SessionToken, user: CurrentUser, db: Db) -> None:
    """Store the user's session token for an app, re-enable its connector and sync now."""
    if app not in CONNECTORS:
        raise HTTPException(status_code=404, detail="no connector for this app")
    store_token(db, user.id, app, session.token)
    # A fresh token is the user's fix for a broken connector, so it lifts the copilot-only fallback.
    db.execute(
        text("DELETE FROM connector_alerts WHERE user_id = :user_id AND app = :app"), {"user_id": user.id, "app": app}
    )
    enqueue(db, user.id, "sync_matches", {"app": app})


@handler("sync_matches", every=SYNC_INTERVAL)
def sync_matches(db: Connection, user_id: int, payload: dict) -> None:
    """Copy matches and new messages into the user's cards. Safe to run twice.

    It syncs the app in `payload["app"]`, or every app with a connector when the payload names none, which is
    how the recurring run is queued.
    """
    for app in [payload["app"]] if "app" in payload else CONNECTORS:
        try:
            _sync_app(db, user_id, app)
        except CapabilityUnavailable:
            # No token, copilot-only or switched off: nothing to sync. The recurring job runs for every user.
            continue


def _sync_app(db: Connection, user_id: int, app: str) -> None:
    connector = CONNECTORS[app]()
    for match in call(db, user_id, connector, "read_matches"):
        card_id = upsert_card(db, user_id, app, match["id"], match["name"])
        if not match["has_messages"]:
            continue
        # One request per match is the costly part, so skip it when the newest message is already stored.
        if match["last_message_id"] and has_message(db, card_id, match["last_message_id"]):
            continue
        for message in call(db, user_id, connector, "read_messages", match["id"]):
            upsert_message(
                db, user_id, card_id, message["id"], message["sender"], message["body"], message["sent_at"]
            )
