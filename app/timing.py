"""Send timing (ADR 0008): when a draft goes out.

`formula()` plans the wait from the conversation. The model that writes the draft may move it by up to half
either way, and `send_time()` then holds it to hard bounds no model output can cross, the night window last
(`night_rule()`, asked again when a planned send goes out). An opener has no conversation to time it:
`opener_time()` picks it, and `outside_night()` keeps it out of the night window.
"""

import random
from datetime import datetime, time, timedelta
from itertools import pairwise
from statistics import median

from sqlalchemy import Connection, text

from app.settings import user_zone

LIVE = timedelta(minutes=5)  # a match who wrote within this is live
LIVE_FLOOR = timedelta(minutes=2)  # the shortest wait for a live match
FLOOR = timedelta(minutes=10)  # the shortest wait otherwise
CEILING = timedelta(hours=12)  # the longest wait, before the night window moves it
MAX_ADJUSTMENT = 0.5  # the model may move the formula's wait by up to half either way
OPENER_WINDOW = (timedelta(minutes=30), timedelta(hours=6))  # an opener goes out this long after the match synced
OPENER_GAP = timedelta(minutes=10)  # the least time between two of a user's openers
OPENER_REASON = "a while after you matched"  # every opener's timing reason: its time is random, not from a chat

# The formula's weights.
_FIRST_PACE = timedelta(minutes=45)  # no reply gap of theirs is known yet
_GAPS = 5  # how many of their most recent reply gaps count
_PACE_BOUNDS = (timedelta(minutes=1), timedelta(hours=6))


def formula(db: Connection, user_id: int, card_id: int, now: datetime) -> timedelta:
    """The formula's wait from `now` before the reply goes out.

    The match's pace (the median of their last five reply gaps, 1 minute to 6 hours, else 45 minutes), times
    their engagement (a question 0.75, 120 characters or more 0.8, under 20 characters with no question 1.25),
    times the hour in the user's time zone (18:00 to midnight 0.8, 09:00 to 18:00 1.2, else 1). That counts
    from their last message, so the time since it is already waited.
    """
    messages = db.execute(
        text(
            "SELECT sender, body, sent_at FROM messages WHERE card_id = :card_id AND user_id = :user_id"
            " ORDER BY sent_at, id"
        ),
        {"card_id": card_id, "user_id": user_id},
    ).all()
    # A gap is how long they took to answer one of the user's messages.
    gaps = [b.sent_at - a.sent_at for a, b in pairwise(messages) if (a.sender, b.sender) == ("me", "them")]
    shortest, longest = _PACE_BOUNDS
    pace = min(max(median(gaps[-_GAPS:]), shortest), longest) if gaps else _FIRST_PACE

    waiting = []  # their messages since the user's last one
    for message in messages:
        waiting = waiting + [message] if message.sender == "them" else []
    words = " ".join(message.body for message in waiting)
    engagement = 1.0
    if "?" in words:
        engagement *= 0.75
    if len(words) >= 120:
        engagement *= 0.8
    elif len(words) < 20 and "?" not in words:
        engagement *= 1.25

    hour = now.astimezone(user_zone(db, user_id)).hour
    daytime = 0.8 if hour >= 18 else 1.2 if hour >= 9 else 1.0

    since = waiting[-1].sent_at if waiting else now
    return max(since + pace * engagement * daytime - now, timedelta(0))


def send_time(db: Connection, user_id: int, card_id: int, wait: timedelta, adjustment: float, now: datetime) -> datetime:
    """When the draft goes out: the formula's `wait` from `now`, moved by the model's `adjustment` (a fraction of
    it, clamped to half either way), then held to the hard bounds: at least 2 minutes when the match is live,
    otherwise 10; at most 12 hours; then the night window (`night_rule()`)."""
    adjustment = min(max(adjustment, -MAX_ADJUSTMENT), MAX_ADJUSTMENT)
    floor = LIVE_FLOOR if _live(db, user_id, card_id, now) else FLOOR
    return night_rule(db, user_id, card_id, now + min(max(wait * (1 + adjustment), floor), CEILING), now)


def night_rule(db: Connection, user_id: int, card_id: int, at: datetime, now: datetime) -> datetime:
    """When a reply planned at `now` to go out at `at` goes out, given the user's night window. Planning asks it
    (`send_time()`), and so does the send itself (`app/send.py`), as the window or time zone may have changed.

    A live match gets the reply at `at`, night or not. Otherwise a time inside the window moves to the window's end
    plus a few random minutes. When that is more than 12 hours from `now`, it moves to a few random minutes before
    the window starts instead, if that is still at least 10 minutes from `now`; if not, to the end after all.
    """
    night = None if _live(db, user_id, card_id, now) else _night(db, user_id, at)
    if not night:
        return at
    start, end = night
    after = end + _few_minutes()
    if after - now <= CEILING:
        return after
    before = start - _few_minutes()
    return before if before - now >= FLOOR else after


def opener_time(db: Connection, user_id: int, synced: datetime) -> datetime:
    """When an opener goes out: a random time 30 minutes to 6 hours after the match `synced`, moved out of the
    night window, then on past each of the user's planned openers closer than 10 minutes. The night window and
    that gap win over the 6 hours."""
    from app.drafts import PLANNED  # imported here: app.drafts imports this module

    # Two workers planning openers for one user take turns, so each sees the other's time.
    db.execute(text("SELECT 1 FROM users WHERE id = :id FOR UPDATE"), {"id": user_id})
    taken = db.execute(
        text(f"SELECT send_at FROM drafts WHERE user_id = :user_id AND kind = 'opener' AND {PLANNED}"),
        {"user_id": user_id},
    ).scalars().all()
    soonest, latest = OPENER_WINDOW
    at = outside_night(db, user_id, synced + soonest + (latest - soonest) * random.random())
    # Each step moves later, so this ends.
    while clash := [other for other in taken if abs(other - at) < OPENER_GAP]:
        at = outside_night(db, user_id, max(clash) + OPENER_GAP)
    return at


def outside_night(db: Connection, user_id: int, at: datetime) -> datetime:
    """`at`, or, when it falls inside the user's night window, the window's end plus a few random minutes."""
    night = _night(db, user_id, at)
    return night[1] + _few_minutes() if night else at


def _live(db: Connection, user_id: int, card_id: int, now: datetime) -> bool:
    """Whether the match is live at `now`: their last message is at most 5 minutes old."""
    last = db.execute(
        text("SELECT max(sent_at) FROM messages WHERE card_id = :card_id AND user_id = :user_id AND sender = 'them'"),
        {"card_id": card_id, "user_id": user_id},
    ).scalar_one()
    return last is not None and now - last <= LIVE


def _night(db: Connection, user_id: int, at: datetime) -> tuple[datetime, datetime] | None:
    """The start and end of the user's night window that `at` falls inside, or None when it falls outside."""
    start, end = db.execute(
        text("SELECT night_window_start, night_window_end FROM users WHERE id = :id"), {"id": user_id}
    ).one()
    zone = user_zone(db, user_id)
    local = at.astimezone(zone)
    # A window whose start is after its end wraps past midnight; equal hours make no window.
    inside = start <= local.hour < end if start <= end else local.hour >= start or local.hour < end
    if not inside:
        return None
    ends = local.date() if local.hour < end else local.date() + timedelta(days=1)
    starts = ends if start < end else ends - timedelta(days=1)
    return datetime.combine(starts, time(start), zone), datetime.combine(ends, time(end), zone)


def _few_minutes() -> timedelta:
    return timedelta(minutes=random.randint(1, 15))
