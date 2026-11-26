"""User settings: columns on the `users` row."""

from zoneinfo import ZoneInfo

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db

router = APIRouter()

_COLUMNS = (
    "stalled_after_days, time_zone, setup_dismissed, push_name_previews, blur_photos,"
    " night_window_start, night_window_end"
)


class Settings(BaseModel):
    # Days without a message before a card is marked Stalled.
    stalled_after_days: int = Field(ge=1)
    # The phone's time zone, an IANA name such as `Europe/Berlin`. The app sends it on each launch.
    time_zone: str
    # The user hid "Finish setup" on Today. The steps stay under You.
    setup_dismissed: bool
    # Hot-lead and handover pushes name the match and quote the suggestions. Off: they name nobody.
    push_name_previews: bool
    # The app blurs faces until tapped (ADR 0009). Only the app reads it.
    blur_photos: bool
    # The night window (`app/timing.py`): nothing is sent from the start hour until the end hour, in the user's
    # time zone. 1 and 7 by default; a start after the end wraps past midnight, equal hours make no window.
    night_window_start: int
    night_window_end: int


class SettingsChange(BaseModel):
    """`PATCH /settings` changes only the fields sent."""

    stalled_after_days: int | None = Field(default=None, ge=1)
    time_zone: str | None = None
    setup_dismissed: bool | None = None
    push_name_previews: bool | None = None
    blur_photos: bool | None = None
    night_window_start: int | None = Field(default=None, ge=0, le=23)
    night_window_end: int | None = Field(default=None, ge=0, le=23)

    @field_validator("time_zone")
    @classmethod
    def known_time_zone(cls, name: str | None) -> str | None:
        if name is not None:
            try:
                ZoneInfo(name)
            except (ValueError, KeyError):  # `ZoneInfoNotFoundError` is a `KeyError`
                raise ValueError(f"unknown time zone: {name}")
        return name


def user_zone(db: Connection, user_id: int) -> ZoneInfo:
    """The user's time zone: what "today", "overdue" and other times of the user's day follow. UTC until the
    app first sends one."""
    return ZoneInfo(db.execute(text("SELECT time_zone FROM users WHERE id = :id"), {"id": user_id}).scalar_one())


@router.get("/settings", response_model=Settings)
def read_settings(user: CurrentUser, db: Db):
    return db.execute(text(f"SELECT {_COLUMNS} FROM users WHERE id = :id"), {"id": user.id}).one()


@router.patch("/settings", response_model=Settings)
def update_settings(change: SettingsChange, user: CurrentUser, db: Db):
    # No setting may be null, so null means "not sent".
    return db.execute(
        text(
            "UPDATE users SET stalled_after_days = COALESCE(:stalled_after_days, stalled_after_days),"
            " time_zone = COALESCE(:time_zone, time_zone),"
            " setup_dismissed = COALESCE(:setup_dismissed, setup_dismissed),"
            " push_name_previews = COALESCE(:push_name_previews, push_name_previews),"
            " blur_photos = COALESCE(:blur_photos, blur_photos),"
            " night_window_start = COALESCE(:night_window_start, night_window_start),"
            f" night_window_end = COALESCE(:night_window_end, night_window_end) WHERE id = :id RETURNING {_COLUMNS}"
        ),
        {"id": user.id, **change.model_dump()},
    ).one()
