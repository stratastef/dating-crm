"""Audit log of autopilot actions: `record_action()` writes it, `GET /audit-log` lists it."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db

ActionType = Literal["message", "like", "pass", "profile_change", "calendar_hold", "purge"]

router = APIRouter()


def record_action(
    connection: Connection, user_id: int, *, type: ActionType, app: str, target: str, trigger: str
) -> None:
    """Append one autopilot action to the user's audit log, in the caller's transaction.

    `app` is the app acted on ("tinder"), `target` who or what was acted on ("match:42"),
    `trigger` what caused the action ("chat autopilot: reply due").
    """
    connection.execute(
        text(
            "INSERT INTO audit_log (user_id, type, app, target, trigger)"
            " VALUES (:user_id, :type, :app, :target, :trigger)"
        ),
        {"user_id": user_id, "type": type, "app": app, "target": target, "trigger": trigger},
    )


class AuditEntry(BaseModel):
    id: int
    type: str
    app: str
    target: str
    trigger: str
    created_at: datetime


@router.get("/audit-log")
def audit_log(user: CurrentUser, db: Db, app: str | None = None, type: str | None = None) -> list[AuditEntry]:
    # shortcut: returns the whole log, add pagination when it grows past a few thousand rows.
    rows = db.execute(
        text(
            "SELECT id, type, app, target, trigger, created_at FROM audit_log"
            " WHERE user_id = :user_id"
            " AND (CAST(:app AS text) IS NULL OR app = :app)"
            " AND (CAST(:type AS text) IS NULL OR type = :type)"
            " ORDER BY id DESC"
        ),
        {"user_id": user.id, "app": app, "type": type},
    )
    return [AuditEntry(**row._mapping) for row in rows]
