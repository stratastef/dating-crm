from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app import calendar
from tests.test_calendar import connect
from tests.test_drafts import write_profile
from tests.test_review import card_with_reply
from tests.test_stalled import new_card, run_scheduled_jobs

# 23:30 on Wednesday 25 November in New York, already Thursday 26 November in UTC; then an hour later.
BEFORE_MIDNIGHT = datetime(2026, 11, 26, 4, 30, tzinfo=UTC)
AFTER_MIDNIGHT = BEFORE_MIDNIGHT + timedelta(hours=1)


@pytest.fixture
def clock(monkeypatch):
    """`clock.at = ...` sets the time Today is computed at."""

    class Clock:
        at = BEFORE_MIDNIGHT

    clock = Clock()
    monkeypatch.setattr("app.today.now", lambda: clock.at)
    return clock


def card(client, name: str = "Ada", **fields) -> int:
    return client.post("/cards", json={"app": "tinder", "name": name, **fields}).json()["id"]


def held(app, client, name: str, start: datetime) -> int:
    """A card with a two-hour slot held for a date with the match, not yet confirmed."""
    card_id = card(client, name)
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        calendar.hold_slot(db, user_id, card_id, start, start + timedelta(hours=2), trigger="chat autopilot: proposed a time")
    return card_id


def booked(app, client, name: str, start: datetime) -> int:
    """A card whose date is confirmed: its one held slot, confirmed by moving the card to Date set."""
    card_id = held(app, client, name, start)
    assert client.patch(f"/cards/{card_id}", json={"stage": "date_set"}).status_code == 200
    return card_id


def groups(client) -> dict[str, list[tuple[str, int]]]:
    """Each group as (kind, card id) pairs, in order."""
    today = client.get("/today").json()
    return {group: [(item["kind"], item["card"]["id"]) for item in today[group]] for group in ("overdue", "today", "coming_up")}


def test_the_review_summary_counts_match_the_review_queue(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post(f"/cards/{card_with_reply(client, 'Ada', minutes_ago=5)}/drafts")
    client.post(f"/cards/{card_with_reply(client, 'Kim', minutes_ago=90)}/drafts")
    queue = client.get("/queue").json()

    review = client.get("/today").json()["review"]

    assert review == {"count": 2, "hot": 1}
    assert review == {"count": len(queue), "hot": sum(item["hot"] for item in queue)}


def test_items_fall_into_overdue_today_and_coming_up_by_the_users_time_zone_on_both_sides_of_midnight(app, client, clock):
    connect(client, app)
    client.patch("/settings", json={"time_zone": "America/New_York"})
    due_wednesday = card(client, next_action="Send the museum link", due_date="2026-11-25")
    wednesday_evening = booked(app, client, "Priya", datetime(2026, 11, 26, 1, tzinfo=UTC))  # 20:00 in New York
    thursday_morning = booked(app, client, "Zoe", datetime(2026, 11, 26, 15, tzinfo=UTC))  # 10:00 in New York

    before = groups(client)
    clock.at = AFTER_MIDNIGHT
    after = groups(client)

    assert before == {
        "overdue": [],
        "today": [("date", wednesday_evening), ("next_action", due_wednesday)],
        "coming_up": [("date", thursday_morning)],
    }
    assert after == {
        "overdue": [("next_action", due_wednesday)],
        "today": [("date", thursday_morning)],
        "coming_up": [],
    }
    assert client.get("/today").json()["today"][0]["starts_at"] == "2026-11-26T15:00:00Z"


def test_coming_up_holds_confirmed_dates_and_next_actions_in_the_next_seven_days_only(app, client, clock):
    connect(client, app)  # it is Thursday 26 November in UTC, the user's time zone
    day_seven = card(client, "Noor", next_action="Ask about the gallery opening", due_date="2026-12-03")
    card(client, "Kim", next_action="Ask about Sunday", due_date="2026-12-04")
    friday = booked(app, client, "Hannah", datetime(2026, 11, 27, 19, tzinfo=UTC))
    booked(app, client, "Iris", datetime(2026, 12, 4, 19, tzinfo=UTC))
    held(app, client, "Lena", datetime(2026, 11, 28, 19, tzinfo=UTC))  # offered, not agreed

    assert groups(client)["coming_up"] == [("date", friday), ("next_action", day_seven)]


def test_stalled_cards_and_dated_cards_with_no_rating_are_under_today(app, client):
    stalled = new_card(client, "chatting", last_message_days_ago=4)
    run_scheduled_jobs(app)
    to_rate = card(client, "Zoe", stage="dated")
    rated = card(client, "Iris", stage="dated")
    client.patch(f"/cards/{rated}", json={"date_rating": 4})

    today = client.get("/today").json()

    assert groups(client)["today"] == [("stalled", stalled), ("rate_date", to_rate)]
    assert today["today"][0]["card"]["suggested_actions"] == ["revive", "archive"]


def test_archived_cards_are_not_on_today(app, client, clock):
    connect(client, app)
    gone = [
        card(client, next_action="Send the museum link", due_date="2026-11-26"),
        card(client, "Zoe", stage="dated"),
        booked(app, client, "Priya", datetime(2026, 11, 26, 19, tzinfo=UTC)),
    ]
    for card_id in gone:
        assert client.patch(f"/cards/{card_id}", json={"stage": "archived"}).status_code == 200

    assert groups(client) == {"overdue": [], "today": [], "coming_up": []}


def test_a_next_action_due_today_is_under_today_not_overdue(client, clock):
    due_today = card(client, next_action="Send the museum link", due_date="2026-11-26")
    late = card(client, "Kim", next_action="Ask about Sunday", due_date="2026-11-24")

    today = client.get("/today").json()

    assert groups(client) == {"overdue": [("next_action", late)], "today": [("next_action", due_today)], "coming_up": []}
    assert today["overdue"][0]["due_date"] == "2026-11-24"
    assert today["overdue"][0]["days_late"] == 2
    assert today["today"][0]["days_late"] is None


def test_the_time_zone_the_app_sends_is_stored_and_used_for_the_next_request(client, clock):
    due = card(client, next_action="Send the museum link", due_date="2026-11-25")
    assert groups(client)["overdue"] == [("next_action", due)]  # Thursday already, in UTC

    assert client.patch("/settings", json={"time_zone": "America/New_York"}).status_code == 200

    assert client.get("/settings").json()["time_zone"] == "America/New_York"
    assert groups(client)["today"] == [("next_action", due)]  # still Wednesday evening there
    assert client.patch("/settings", json={"time_zone": "Mars/Olympus_Mons"}).status_code == 422
