"""Today: what the user has to do, by time, in the user's time zone (ADR 0005)."""

from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app import review, setup
from app.auth import CurrentUser, Db
from app.cards import _COLUMNS, Card, summarize
from app.settings import user_zone

router = APIRouter()

COMING_UP_DAYS = 7


def now() -> datetime:
    """The time Today is computed at. Tests replace it."""
    return datetime.now(UTC)


class ReviewSummary(BaseModel):
    count: int  # items waiting in the review queue
    hot: int  # how many of them are hot leads


class TodayItem(BaseModel):
    # `date`: a confirmed calendar hold. `next_action`: the card's next action, by its due day.
    # `stalled`: a Stalled card, to revive or archive. `rate_date`: a Dated card with no rating.
    kind: Literal["date", "next_action", "stalled", "rate_date"]
    card: Card
    starts_at: datetime | None = None  # `date`: when it starts
    due_date: date | None = None  # `next_action`: its due day
    days_late: int | None = None  # under Overdue: whole days past the due day


class Today(BaseModel):
    review: ReviewSummary
    setup: setup.SetupSummary | None  # "Finish setup": null once dismissed or done
    overdue: list[TodayItem]
    today: list[TodayItem]
    coming_up: list[TodayItem]


@router.get("/today", response_model=Today)
def today(user: CurrentUser, db: Db):
    zone = user_zone(db, user.id)
    day = now().astimezone(zone).date()
    last = day + timedelta(days=COMING_UP_DAYS)
    dates = db.execute(
        text(
            "SELECT card_id, lower(slot) AS starts_at FROM calendar_holds WHERE user_id = :user_id"
            " AND status = 'confirmed' AND lower(slot) >= :start AND lower(slot) < :end ORDER BY lower(slot), id"
        ),
        {
            "user_id": user.id,
            "start": datetime.combine(day, time(), zone),
            "end": datetime.combine(last + timedelta(days=1), time(), zone),
        },
    ).all()
    # Archived cards are done with: nothing of theirs is on Today.
    rows = db.execute(
        text(
            f"""
            SELECT {_COLUMNS} FROM cards WHERE user_id = :user_id AND stage <> 'archived'
              AND (id = ANY(:dated) OR (next_action IS NOT NULL AND due_date <= :last) OR stalled_at IS NOT NULL
                   OR (stage = 'dated' AND date_rating IS NULL))
            ORDER BY id
            """
        ),
        {"user_id": user.id, "dated": [row.card_id for row in dates], "last": last},
    ).all()
    cards = summarize(db, user.id, rows)
    by_id = {card.id: card for card in cards}

    # (day, item) by day. The sort is stable, so on one day dates come first, by time, then next actions.
    timed = sorted(
        [
            (row.starts_at.astimezone(zone).date(), TodayItem(kind="date", card=by_id[row.card_id], starts_at=row.starts_at))
            for row in dates
            if row.card_id in by_id
        ]
        + [
            (card.due_date, TodayItem(kind="next_action", card=card, due_date=card.due_date))
            for card in cards
            if card.next_action is not None and card.due_date is not None and card.due_date <= last
        ],
        key=lambda pair: pair[0],
    )
    # The queue itself, so the summary row and the Review tab never disagree.
    queue = review.queue(user, db)
    return Today(
        review=ReviewSummary(count=len(queue), hot=sum(item.hot for item in queue)),
        setup=setup.summary(user, db),
        overdue=[item.model_copy(update={"days_late": (day - when).days}) for when, item in timed if when < day],
        today=[item for when, item in timed if when == day]
        + [TodayItem(kind="stalled", card=card) for card in cards if card.stalled]
        + [TodayItem(kind="rate_date", card=card) for card in cards if card.stage == "dated" and card.date_rating is None],
        coming_up=[item for when, item in timed if when > day],
    )
