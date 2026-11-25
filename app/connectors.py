"""Connector contract: subclass `Connector`, declare `capabilities`, and run every capability through `call()`."""

import logging
import os
from typing import Literal

from sqlalchemy import Connection, Row, text

from app.vault import read_token

log = logging.getLogger("connectors")

Capability = Literal["read_matches", "read_messages", "send", "like", "pass"]


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

    def send(self, token: str, match_id: str, text: str) -> None:
        raise NotImplementedError

    def like(self, token: str, profile_id: str) -> None:
        raise NotImplementedError

    def pass_(self, token: str, profile_id: str) -> None:
        raise NotImplementedError


class CapabilityUnavailable(Exception):
    """The capability was not attempted: not declared, disabled by configuration, or the app is copilot-only."""


class CapabilityFailed(Exception):
    """The connector raised. The app is now copilot-only for this user; `__cause__` is the connector's error."""


def disabled_capabilities() -> set[str]:
    """`CONNECTOR_DISABLED_CAPABILITIES=tinder:send,hinge:like` switches those capabilities off."""
    return {item.strip() for item in os.environ.get("CONNECTOR_DISABLED_CAPABILITIES", "").split(",") if item.strip()}


def call(db: Connection, user_id: int, connector: Connector, capability: Capability, *args):
    """Run one capability of a connector for a user and return its result.

    The user's session token is read from the vault and passed to the connector as its first argument;
    `args` are the rest. Raises `CapabilityUnavailable` without touching the app when the capability is not
    declared, is disabled, the app is copilot-only, or the user has no stored token. If the connector raises, the app becomes copilot-only for this user, an alert
    is stored, and `CapabilityFailed` is raised.
    """
    name = f"{connector.app}:{capability}"
    if capability not in connector.capabilities:
        raise CapabilityUnavailable(f"{connector.app} does not support {capability}")
    if name in disabled_capabilities():
        raise CapabilityUnavailable(f"{name} is disabled by configuration")
    if is_copilot_only(db, user_id, connector.app):
        raise CapabilityUnavailable(f"{connector.app} is copilot-only")
    token = read_token(db, user_id, connector.app)
    if token is None:
        raise CapabilityUnavailable(f"no {connector.app} session token is stored")
    try:
        return getattr(connector, "pass_" if capability == "pass" else capability)(token, *args)
    except Exception as error:
        log.warning("%s failed for user %s, falling back to copilot: %r", name, user_id, error)
        # Own transaction: the caller (a job handler) rolls back when this raises, and the fallback must survive that.
        with db.engine.begin() as own:
            own.execute(
                text(
                    "INSERT INTO connector_alerts (user_id, app, capability, error)"
                    " VALUES (:user_id, :app, :capability, :error)"
                ),
                {"user_id": user_id, "app": connector.app, "capability": capability, "error": repr(error)},
            )
        raise CapabilityFailed(name) from error


def alerts(db: Connection, user_id: int) -> list[Row]:
    """The user's connector alerts, newest first: `app`, `capability`, `error`, `created_at`."""
    return list(
        db.execute(
            text(
                "SELECT id, app, capability, error, created_at FROM connector_alerts"
                " WHERE user_id = :user_id ORDER BY id DESC"
            ),
            {"user_id": user_id},
        )
    )


def is_copilot_only(db: Connection, user_id: int, app: str) -> bool:
    """True while the user has an alert for this app. Delete the app's alerts to re-enable its connector."""
    return db.execute(
        text("SELECT EXISTS (SELECT 1 FROM connector_alerts WHERE user_id = :user_id AND app = :app)"),
        {"user_id": user_id, "app": app},
    ).scalar_one()
