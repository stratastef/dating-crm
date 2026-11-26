"""Setup: the steps that take a new user from sign-in to a working pipeline (ADR 0001), each done or not."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import calendar, swipes, sync, voice
from app.auth import CurrentUser, Db, User
from app.preferences import current_preferences

router = APIRouter()


class SetupStep(BaseModel):
    step: Literal["dating_apps", "calendar", "voice", "preferences", "swipe_layout_and_autonomy"]
    done: bool


def autonomy_chosen(db: Connection, user_id: int) -> bool:
    """Whether the user has set any autonomy level. Until then every job runs at its default, which they never saw."""
    return db.execute(
        text("SELECT EXISTS (SELECT 1 FROM autonomy_settings WHERE user_id = :user_id)"), {"user_id": user_id}
    ).scalar_one()


def steps(user: User, db: Connection) -> list[SetupStep]:
    """The five steps in the order the app runs them."""
    # Calls the route function, so a step is done exactly when Connected apps shows it.
    apps = sync.connected_apps(user, db)
    return [
        SetupStep(step="dating_apps", done=any(app["state"] in ("connected", "copilot_only") for app in apps)),
        SetupStep(step="calendar", done=calendar.status(user, db)["connected"]),
        # The app never sends a blank answer.
        SetupStep(step="voice", done=bool(voice.read_voice(user, db).answers)),
        SetupStep(step="preferences", done=current_preferences(db, user.id).version > 0),
        SetupStep(
            step="swipe_layout_and_autonomy",
            done=swipes.read_layout(user, db)["layout"] is not None and autonomy_chosen(db, user.id),
        ),
    ]


class SetupSummary(BaseModel):
    steps_left: int  # steps not done yet, at least 1


def summary(user: User, db: Connection) -> SetupSummary | None:
    """Today's "Finish setup" row: the steps left, or none once the user dismissed it or no step is left."""
    if db.execute(text("SELECT setup_dismissed FROM users WHERE id = :id"), {"id": user.id}).scalar_one():
        return None
    left = sum(not step.done for step in steps(user, db))
    return SetupSummary(steps_left=left) if left else None


@router.get("/setup", response_model=list[SetupStep])
def read_setup(user: CurrentUser, db: Db):
    return steps(user, db)
