"""The status strip: what stops autopilot now, in the order the phone shows it. The copy lives in the app."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import llm
from app.auth import CurrentUser, Db
from app.autopilot import pauses
from app.sync import connected_apps

router = APIRouter()


def now() -> datetime:
    """The time the reset is computed from. Tests replace it."""
    return datetime.now(UTC)


class StatusMessage(BaseModel):
    kind: Literal["paused", "budget_reached", "connector_alert"]
    app: str | None = None  # `paused`: the paused app, None for all apps. `connector_alert`: the broken app
    resets_at: datetime | None = None  # `budget_reached`: when the next month's budget starts


@router.get("/status", response_model=list[StatusMessage])
def status(user: CurrentUser, db: Db):
    messages = []
    paused = pauses(db, user.id)
    if paused["all"]:
        messages.append(StatusMessage(kind="paused"))
    messages += [StatusMessage(kind="paused", app=app) for app in paused["apps"]]  # by name
    if llm.budget_reached(db, user.id):
        # Spend counts the calendar month in UTC (`llm.spend()`), so the budget resets at the next one.
        today = now()
        resets_at = datetime(today.year + today.month // 12, today.month % 12 + 1, 1, tzinfo=UTC)
        messages.append(StatusMessage(kind="budget_reached", resets_at=resets_at))
    # Connected apps' `broken` state, so the strip and that screen agree; a copilot-only choice answers the alert.
    messages += [
        StatusMessage(kind="connector_alert", app=row["app"])
        for row in connected_apps(user, db)
        if row["state"] == "broken"
    ]
    return messages
