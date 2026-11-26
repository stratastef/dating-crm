"""The one number: good dates per hour of the user's time, week by week, with this month's funnel and AI spend."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import CurrentUser, Db
from app.budget import budget
from app.cards import is_good_date

router = APIRouter()

# Weeks start on Monday, in UTC.
_WEEK = "CAST(date_trunc('week', {} AT TIME ZONE 'UTC') AS date)"
# Months too, as the AI budget's (`llm.spend`).
_MONTH = "date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


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


class Funnel(BaseModel):
    """Cards that reached each stage this month. A card counts in every stage it reached, archived or not."""

    matched: int
    chatting: int
    date_set: int
    dated: int
    good: int  # good dates rated this month


class Dashboard(BaseModel):
    weeks: list[Week]
    this_week: float | None  # good dates per hour this week; null when no time was recorded
    four_week_average: float | None  # good dates per hour over the four weeks before this one
    funnel: Funnel
    spend_per_good_date_usd: float | None  # this month's AI spend over this month's good dates; null without one
    budget: dict  # as `GET /budget`: this month's AI spend and the cap


@router.get("/dashboard", response_model=Dashboard)
def dashboard(user: CurrentUser, db: Db):
    """Every week with recorded time or a good date, oldest first, then the headline, funnel and spend."""
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
    good_this_month = 0
    for week, this_month, rating in db.execute(
        text(
            f"SELECT {_WEEK.format('date_rated_at')}, date_rated_at >= {_MONTH}, date_rating FROM cards"
            " WHERE user_id = :user_id AND date_rated_at IS NOT NULL"
        ),
        {"user_id": user.id},
    ):
        if is_good_date(rating):
            good_dates[week] = good_dates.get(week, 0) + 1
            good_this_month += this_month

    def per_hour(weeks: list[date]) -> float | None:
        time = sum(hours.get(week, 0) for week in weeks)
        return sum(good_dates.get(week, 0) for week in weeks) / time if time else None

    today = datetime.now(UTC).date()
    monday = today - timedelta(days=today.weekday())
    matched, chatting, date_set, dated = db.execute(
        text(
            f"SELECT count(*) FILTER (WHERE created_at >= {_MONTH}), count(*) FILTER (WHERE chatting_at >= {_MONTH}),"
            f" count(*) FILTER (WHERE date_set_at >= {_MONTH}), count(*) FILTER (WHERE dated_at >= {_MONTH})"
            " FROM cards WHERE user_id = :user_id"
        ),
        {"user_id": user.id},
    ).one()
    spend = budget(db, user.id)
    return Dashboard(
        weeks=[
            Week(
                week=week,
                good_dates=good_dates.get(week, 0),
                hours=hours.get(week, 0),
                good_dates_per_hour=good_dates.get(week, 0) / hours[week] if week in hours else None,
            )
            for week in sorted(hours.keys() | good_dates.keys())
        ],
        this_week=per_hour([monday]),
        four_week_average=per_hour([monday - timedelta(weeks=n) for n in range(1, 5)]),
        funnel=Funnel(matched=matched, chatting=chatting, date_set=date_set, dated=dated, good=good_this_month),
        spend_per_good_date_usd=spend["spend_usd"] / good_this_month if good_this_month else None,
        budget=spend,
    )
