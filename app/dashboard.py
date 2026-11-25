"""The one number: good dates per hour of the user's time, week by week."""

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import CurrentUser, Db
from app.cards import is_good_date

router = APIRouter()

# Weeks start on Monday, in UTC.
_WEEK = "CAST(date_trunc('week', {} AT TIME ZONE 'UTC') AS date)"


class AppTime(BaseModel):
    seconds: int = Field(ge=1, le=86400)


@router.post("/time", status_code=204)
def record_time(time: AppTime, user: CurrentUser, db: Db) -> None:
    """Record a stretch of time the user spent in the app. The app reports its own foreground time."""
    db.execute(
        text("INSERT INTO app_time (user_id, seconds) VALUES (:user_id, :seconds)"),
        {"user_id": user.id, "seconds": time.seconds},
    )


class Week(BaseModel):
    week: date  # the Monday the week starts on
    good_dates: int
    hours: float
    good_dates_per_hour: float | None  # null when no time was recorded that week


@router.get("/dashboard", response_model=list[Week])
def dashboard(user: CurrentUser, db: Db):
    """Every week with recorded time or a good date, oldest first."""
    hours = {
        week: seconds / 3600
        for week, seconds in db.execute(
            text(
                f"SELECT {_WEEK.format('recorded_at')} AS week, sum(seconds) FROM app_time"
                " WHERE user_id = :user_id GROUP BY week"
            ),
            {"user_id": user.id},
        )
    }
    good_dates: dict[date, int] = {}
    for week, rating in db.execute(
        text(
            f"SELECT {_WEEK.format('date_rated_at')}, date_rating FROM cards"
            " WHERE user_id = :user_id AND date_rated_at IS NOT NULL"
        ),
        {"user_id": user.id},
    ):
        if is_good_date(rating):
            good_dates[week] = good_dates.get(week, 0) + 1
    return [
        Week(
            week=week,
            good_dates=good_dates.get(week, 0),
            hours=hours.get(week, 0),
            good_dates_per_hour=good_dates.get(week, 0) / hours[week] if week in hours else None,
        )
        for week in sorted(hours.keys() | good_dates.keys())
    ]
