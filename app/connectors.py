"""Connector contract: subclass `Connector`, declare `capabilities`, and run every capability through `call()`."""

import logging
import os
from typing import Literal, get_args

import httpx
from sqlalchemy import Connection, Row, text

from app.autopilot import pause
from app.push import send_push
from app.vault import read_token

log = logging.getLogger("connectors")

# A paid item spends something the account holds (bought or granted). It is a capability like the others, but
# `call()` refuses it: only `app.paid_items.spend()` runs one, with a proposal the user approved.
PaidItem = Literal["super_like", "rose", "boost"]
PAID_ITEMS = frozenset(get_args(PaidItem))
Capability = Literal["read_matches", "read_messages", "read_candidates", "send", "like", "pass", PaidItem]
Reason = Literal["auth failure", "ban signal", "transient"]


class Connector:
    """One dating app's private-API connector.

    Set `app` and `capabilities`, and implement the method for each declared capability.
    `token` is the user's session token from the vault. Raise any exception when the app refuses or breaks.
    """

    app: str
    capabilities: frozenset[Capability] = frozenset()

    def read_matches(self, token: str) -> list[dict]:
        raise NotImplementedError

    def read_messages(self, token: str, match_id: str) -> list[dict]:
        raise NotImplementedError

    def read_candidates(self, token: str) -> list[dict]:
        """Each profile: `id`, `name`, `bio`, `photos` (URLs), and `cost` when the app shows what a paid item
        on this profile costs ("$1.99"). A proposal for the profile carries it (`app/paid_items.py`)."""
        raise NotImplementedError

    def send(self, token: str, match_id: str, text: str) -> dict:
        """Returns the sent message: `id` (the app's ID for it) and `sent_at` (ISO 8601)."""
        raise NotImplementedError

    def like(self, token: str, profile_id: str) -> None:
        raise NotImplementedError

    def pass_(self, token: str, profile_id: str) -> None:
        raise NotImplementedError

    # Paid items. Each spends one item the account already holds and returns False when it holds none.
    # A connector must never buy an item or touch a payment method.

    def super_like(self, token: str, profile_id: str) -> bool:
        raise NotImplementedError

    def rose(self, token: str, profile_id: str) -> bool:
        raise NotImplementedError

    def boost(self, token: str) -> bool:
        raise NotImplementedError


class CapabilityUnavailable(Exception):
    """The capability was not attempted: not declared, disabled by configuration, or the app is copilot-only."""


class PaidItemNeedsApproval(Exception):
    """A paid item was asked for through `call()`. A bug in the caller: use `app.paid_items.spend()`."""


class CapabilityFailed(Exception):
    """The connector raised; `__cause__` is its error. Unless the error was transient, the app is now
    copilot-only for this user."""


def classify(error: Exception) -> Reason:
    """What a connector's error means: HTTP 401 is an auth failure, HTTP 403 a ban signal, anything else transient."""
    # shortcut: status codes only, upgrade when an app signals a ban some other way (an error code in the body).
    status = error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None
    if status == 401:
        return "auth failure"
    return "ban signal" if status == 403 else "transient"


def disabled_capabilities() -> set[str]:
    """`CONNECTOR_DISABLED_CAPABILITIES=tinder:send,hinge:like` switches those capabilities off."""
    return {item.strip() for item in os.environ.get("CONNECTOR_DISABLED_CAPABILITIES", "").split(",") if item.strip()}


def unavailable(db: Connection, user_id: int, connector: Connector, capability: Capability) -> str | None:
    """Why `call()` would not attempt this capability for the user, or None if it would."""
    name = f"{connector.app}:{capability}"
    if capability not in connector.capabilities:
        return f"{connector.app} does not support {capability}"
    if name in disabled_capabilities():
        return f"{name} is disabled by configuration"
    if is_copilot_only(db, user_id, connector.app):
        return f"{connector.app} is copilot-only"
    if read_token(db, user_id, connector.app) is None:
        return f"no {connector.app} session token is stored"
    return None


def call(db: Connection, user_id: int, connector: Connector, capability: Capability, *args):
    """Run one capability of a connector for a user and return its result.

    The user's session token is read from the vault and passed to the connector as its first argument;
    `args` are the rest. Raises `CapabilityUnavailable` without touching the app when the capability is not
    declared, is disabled, the app is copilot-only, or the user has no stored token. If the connector raises,
    `CapabilityFailed` is raised. For an auth failure or ban signal (see `classify()`) the app also becomes
    copilot-only for this user, an alert is stored, and the app's autopilot is paused. A transient error
    changes nothing: the next call reaches the app again.

    Never spends a paid item: asked for one, it raises `PaidItemNeedsApproval` before anything else.
    """
    if capability in PAID_ITEMS:
        raise PaidItemNeedsApproval(f"{connector.app}:{capability} is spent only by app.paid_items.spend()")
    return _run(db, user_id, connector, capability, *args)


def _run(db: Connection, user_id: int, connector: Connector, capability: Capability, *args):
    """`call()` without the paid-item refusal. Its only callers are `call()` and `app.paid_items.spend()`;
    `tests/test_paid_items.py` fails if another module names it."""
    name = f"{connector.app}:{capability}"
    why = unavailable(db, user_id, connector, capability)
    if why:
        raise CapabilityUnavailable(why)
    token = read_token(db, user_id, connector.app)
    try:
        return getattr(connector, "pass_" if capability == "pass" else capability)(token, *args)
    except Exception as error:
        reason = classify(error)
        log.warning("%s failed for user %s (%s): %r", name, user_id, reason, error)
        if reason == "transient":
            # A timeout or a 5xx passes by itself: nothing is stored, the app stays on, and the caller (a
            # job) fails and is retried.
            raise CapabilityFailed(name) from error
        # Own transaction: the caller (a job handler) rolls back when this raises, and the fallback must survive that.
        with db.engine.begin() as own:
            own.execute(
                text(
                    "INSERT INTO connector_alerts (user_id, app, capability, error, reason)"
                    " VALUES (:user_id, :app, :capability, :error, :reason)"
                ),
                {
                    "user_id": user_id,
                    "app": connector.app,
                    "capability": capability,
                    # The kind of error only. Its text and URL can hold match and profile IDs, and an alert
                    # outlives a purge of that person. The full error is in the log line above.
                    "error": type(error).__name__
                    + (f" {error.response.status_code}" if isinstance(error, httpx.HTTPStatusError) else ""),
                    "reason": reason,
                },
            )
            pause(own, user_id, connector.app, reason=reason)
            send_push(own, user_id, f"{connector.app} autopilot paused", reason)
        raise CapabilityFailed(name) from error


def alerts(db: Connection, user_id: int) -> list[Row]:
    """The user's connector alerts, newest first: `app`, `capability`, `error`, `reason`, `created_at`."""
    return list(
        db.execute(
            text(
                "SELECT id, app, capability, error, reason, created_at FROM connector_alerts"
                " WHERE user_id = :user_id ORDER BY id DESC"
            ),
            {"user_id": user_id},
        )
    )


def is_copilot_only(db: Connection, user_id: int, app: str) -> bool:
    """True while the user has an alert for this app. Delete the app's alerts to re-enable its connector."""
    # Transient errors are no longer stored; a row left from before must not keep the app off.
    return db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM connector_alerts"
            " WHERE user_id = :user_id AND app = :app AND reason <> 'transient')"
        ),
        {"user_id": user_id, "app": app},
    ).scalar_one()
