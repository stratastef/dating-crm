"""Autonomy level per job and Pause: both decide whether autopilot may act."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app import llm
from app.auth import CurrentUser, Db

Job = Literal["chat", "profile", "swipe"]
Level = Literal["off", "copilot", "autopilot", "full_autopilot"]

DEFAULT_LEVELS: dict[str, str] = {"chat": "copilot", "profile": "copilot", "swipe": "off"}

router = APIRouter()


def autonomy_levels(db: Connection, user_id: int) -> dict[str, str]:
    """The user's autonomy level for every job, with defaults for jobs they never set."""
    rows = db.execute(text("SELECT job, level FROM autonomy_settings WHERE user_id = :user_id"), {"user_id": user_id})
    return DEFAULT_LEVELS | {row.job: row.level for row in rows}


def set_autonomy(db: Connection, user_id: int, job: Job, level: Level) -> None:
    db.execute(
        text(
            "INSERT INTO autonomy_settings (user_id, job, level) VALUES (:user_id, :job, :level)"
            " ON CONFLICT (user_id, job) DO UPDATE SET level = EXCLUDED.level"
        ),
        {"user_id": user_id, "job": job, "level": level},
    )


def pause(db: Connection, user_id: int, app: str | None = None, reason: str = "paused by user") -> None:
    """Pause autopilot for one app, or for all apps when `app` is None. `reason` is shown on skipped jobs."""
    db.execute(
        text(
            "INSERT INTO autopilot_pauses (user_id, app, reason) VALUES (:user_id, :app, :reason)"
            " ON CONFLICT (user_id, app) DO NOTHING"  # the first reason stays
        ),
        {"user_id": user_id, "app": app or "", "reason": reason},
    )


def resume(db: Connection, user_id: int, app: str | None = None) -> None:
    """Lift the pause on one app, or the pause on all apps when `app` is None. Apps paused on their own stay paused."""
    db.execute(
        text("DELETE FROM autopilot_pauses WHERE user_id = :user_id AND app = :app"),
        {"user_id": user_id, "app": app or ""},
    )


def pauses(db: Connection, user_id: int) -> dict:
    rows = db.execute(text("SELECT app FROM autopilot_pauses WHERE user_id = :user_id"), {"user_id": user_id})
    apps = sorted(row.app for row in rows)
    return {"all": "" in apps, "apps": [app for app in apps if app]}


def autopilot_block(db: Connection, user_id: int, app: str | None, job: Job) -> str | None:
    """Why autopilot may not act for this user, app and job, or None if it may."""
    paused = db.execute(
        text(
            "SELECT app, reason FROM autopilot_pauses WHERE user_id = :user_id AND app IN ('', :app)"
            " ORDER BY app LIMIT 1"  # the pause on all apps first
        ),
        {"user_id": user_id, "app": app or ""},
    ).one_or_none()
    if paused:
        return f"autopilot paused for {paused.app or 'all apps'}: {paused.reason}"
    # The budget pause is not a stored pause: it ends by itself in a new month or when the cap is raised.
    if llm.budget_reached(db, user_id):
        return "autopilot paused for all apps: AI budget reached"
    level = autonomy_levels(db, user_id)[job]
    if level not in ("autopilot", "full_autopilot"):
        return f"{job} autonomy is {level}"
    return None


def autopilot_allowed(db: Connection, user_id: int, app: str | None, job: Job) -> bool:
    """True if the app may act alone: nothing is paused and the job's autonomy is autopilot or full_autopilot."""
    return autopilot_block(db, user_id, app, job) is None


@router.get("/autopilot/pause")
def get_pauses(user: CurrentUser, db: Db) -> dict:
    return pauses(db, user.id)


@router.post("/autopilot/pause")
def post_pause(user: CurrentUser, db: Db, app: str | None = None) -> dict:
    pause(db, user.id, app)
    return pauses(db, user.id)


@router.post("/autopilot/resume")
def post_resume(user: CurrentUser, db: Db, app: str | None = None) -> dict:
    resume(db, user.id, app)
    return pauses(db, user.id)


class AutonomyUpdate(BaseModel):
    level: Level


@router.get("/autonomy")
def get_autonomy(user: CurrentUser, db: Db) -> dict[str, str]:
    return autonomy_levels(db, user.id)


@router.put("/autonomy/{job}")
def put_autonomy(job: Job, update: AutonomyUpdate, user: CurrentUser, db: Db) -> dict[str, str]:
    set_autonomy(db, user.id, job, update.level)
    return autonomy_levels(db, user.id)
