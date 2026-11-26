"""Read sync: the recurring `sync_matches` job copies each app's matches and messages into cards.
Submitting a session token also runs it at once."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db
from app.cards import has_message, upsert_card, upsert_message
from app.connectors import CapabilityUnavailable, Connector, alerts, call
from app.jobs import enqueue, handler
from app.tinder import TinderConnector
from app.vault import delete_token, read_token, store_token

router = APIRouter()

# The apps that have a connector. Add each new connector here.
CONNECTORS: dict[str, type[Connector]] = {"tinder": TinderConnector}

# Every dating app Connected apps lists. On one without a connector the app drafts and the user copies.
DATING_APPS = ("tinder", "hinge", "bumble")

SYNC_INTERVAL = timedelta(minutes=15)


class SessionToken(BaseModel):
    token: str = Field(min_length=1)


@router.put("/connectors/{app}/token", status_code=204)
def submit_token(app: str, session: SessionToken, user: CurrentUser, db: Db) -> None:
    """Store the user's session token for an app, re-enable its connector and sync now."""
    if app not in CONNECTORS:
        raise HTTPException(status_code=404, detail="no connector for this app")
    store_token(db, user.id, app, session.token)
    # A fresh token is the user's fix for a broken connector, and their way back from copilot-only.
    where = {"user_id": user.id, "app": app}
    db.execute(text("DELETE FROM connector_alerts WHERE user_id = :user_id AND app = :app"), where)
    db.execute(text("DELETE FROM copilot_only_apps WHERE user_id = :user_id AND app = :app"), where)
    enqueue(db, user.id, "sync_matches", {"app": app})


@router.put("/connectors/{app}/copilot-only", status_code=204)
def choose_copilot_only(app: str, user: CurrentUser, db: Db) -> None:
    """The user keeps an app copilot-only: nothing syncs, sends or swipes there, and its session token is
    deleted. The choice answers the app's alerts. A fresh token turns the connector back on."""
    if app not in CONNECTORS:
        raise HTTPException(status_code=404, detail="no connector for this app")
    delete_token(db, user.id, app)
    where = {"user_id": user.id, "app": app}
    db.execute(text("DELETE FROM connector_alerts WHERE user_id = :user_id AND app = :app"), where)
    db.execute(
        text("INSERT INTO copilot_only_apps (user_id, app) VALUES (:user_id, :app) ON CONFLICT DO NOTHING"), where
    )


@router.get("/connectors")
def connected_apps(user: CurrentUser, db: Db) -> list[dict]:
    """Each app in `DATING_APPS` with its connector `state` and, when `broken`, its newest `alert`.

    `state` is `no_connector`, `copilot_only` (the user's choice), `broken` (an alert stopped the connector),
    `connected` (a token is stored) or `not_connected`.
    """
    newest: dict[str, dict] = {}
    for alert in alerts(db, user.id):  # newest first
        if alert.reason != "transient":  # a row left from before transient errors stopped being stored
            newest.setdefault(alert.app, dict(alert._mapping))
    chosen = set(
        db.execute(text("SELECT app FROM copilot_only_apps WHERE user_id = :user_id"), {"user_id": user.id}).scalars()
    )

    def state(app: str) -> str:
        if app not in CONNECTORS:
            return "no_connector"
        if app in chosen:
            return "copilot_only"
        if app in newest:
            return "broken"
        return "connected" if read_token(db, user.id, app) else "not_connected"

    return [{"app": app, "state": state(app), "alert": newest.get(app)} for app in DATING_APPS]


@router.get("/connectors/alerts")
def get_alerts(user: CurrentUser, db: Db) -> list[dict]:
    """The user's connector alerts, newest first: `app`, `capability`, `reason`, `error`, `created_at`."""
    return [dict(alert._mapping) for alert in alerts(db, user.id)]


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
        if card_id is None or not match["has_messages"]:  # None: the user purged this match
            continue
        # One request per match is the costly part, so skip it when the newest message is already stored.
        if match["last_message_id"] and has_message(db, user_id, card_id, match["last_message_id"]):
            continue
        for message in call(db, user_id, connector, "read_messages", match["id"]):
            upsert_message(
                db, user_id, card_id, message["id"], message["sender"], message["body"], message["sent_at"]
            )
