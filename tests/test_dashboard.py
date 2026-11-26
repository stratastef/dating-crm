from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app import llm


def this_monday() -> str:
    today = datetime.now(UTC).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def rate(client, name: str, rating: int) -> None:
    card_id = client.post("/cards", json={"app": "tinder", "name": name, "stage": "dated"}).json()["id"]
    client.patch(f"/cards/{card_id}", json={"date_rating": rating})


def add(client, name: str, stage: str = "matched") -> int:
    return client.post("/cards", json={"app": "tinder", "name": name, "stage": stage}).json()["id"]


def move(client, card_id: int, *stages: str) -> None:
    for stage in stages:
        client.patch(f"/cards/{card_id}", json={"stage": stage})


LAST_MONTH = "date_trunc('month', now()) - interval '1 day'"


def test_time_the_app_reports_is_recorded_and_summed_for_the_week(client):
    assert client.post("/time", json={"seconds": 1800}).status_code == 204
    client.post("/time", json={"seconds": 5400})

    assert client.get("/dashboard").json()["weeks"] == [
        {"week": this_monday(), "good_dates": 0, "hours": 2.0, "good_dates_per_hour": 0.0}
    ]


def test_reported_time_must_be_between_one_second_and_one_day(client):
    assert client.post("/time", json={"seconds": 0}).status_code == 422
    assert client.post("/time", json={"seconds": 86401}).status_code == 422


def test_good_dates_per_hour_counts_only_ratings_of_4_or_5(client):
    client.post("/time", json={"seconds": 4 * 3600})
    for name, rating in [("Ana", 5), ("Bea", 4), ("Cy", 3), ("Di", 1)]:
        rate(client, name, rating)

    assert client.get("/dashboard").json()["weeks"] == [
        {"week": this_monday(), "good_dates": 2, "hours": 4.0, "good_dates_per_hour": 0.5}
    ]


def test_weeks_run_monday_to_sunday_oldest_first(app, client):
    client.post("/time", json={"seconds": 3600})
    client.post("/time", json={"seconds": 7200})
    rate(client, "Ana", 5)
    rate(client, "Bea", 4)
    with app.state.engine.begin() as db:
        # Sunday 8 November 2026 belongs to the week of Monday 2 November; Monday 9 November starts the next.
        db.execute(text("UPDATE app_time SET recorded_at = '2026-11-08 23:00+00' WHERE seconds = 3600"))
        db.execute(text("UPDATE app_time SET recorded_at = '2026-11-09 01:00+00' WHERE seconds = 7200"))
        db.execute(text("UPDATE cards SET date_rated_at = '2026-11-08 12:00+00' WHERE name = 'Ana'"))
        db.execute(text("UPDATE cards SET date_rated_at = '2026-11-10 12:00+00' WHERE name = 'Bea'"))

    assert client.get("/dashboard").json()["weeks"] == [
        {"week": "2026-11-02", "good_dates": 1, "hours": 1.0, "good_dates_per_hour": 1.0},
        {"week": "2026-11-09", "good_dates": 1, "hours": 2.0, "good_dates_per_hour": 0.5},
    ]


def test_a_week_with_good_dates_and_no_recorded_time_has_no_rate(client):
    rate(client, "Ana", 5)

    assert client.get("/dashboard").json()["weeks"] == [
        {"week": this_monday(), "good_dates": 1, "hours": 0.0, "good_dates_per_hour": None}
    ]


def test_a_date_stays_in_the_week_it_was_first_rated(app, client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Ana", "stage": "dated"}).json()["id"]
    client.patch(f"/cards/{card_id}", json={"date_rating": 5})
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE cards SET date_rated_at = '2026-11-03 12:00+00'"))

    client.patch(f"/cards/{card_id}", json={"date_rating": 4, "notes": "saved again"})

    assert [week["week"] for week in client.get("/dashboard").json()["weeks"]] == ["2026-11-02"]


def test_the_dashboard_shows_only_the_callers_time_and_dates(client_for):
    alice = client_for("alice@example.com")
    alice.post("/time", json={"seconds": 3600})
    rate(alice, "Ana", 5)

    bob = client_for("bob@example.com").get("/dashboard").json()
    assert bob["weeks"] == []
    assert bob["funnel"] == {"matched": 0, "chatting": 0, "date_set": 0, "dated": 0, "good": 0}


def test_this_weeks_good_dates_per_hour_is_set_against_the_four_weeks_before_it(app, client):
    # This week: 1 good date in 1 hour. The four weeks before: 1 good date in 4 hours.
    for seconds in [3600, 5400, 9000, 3601]:
        client.post("/time", json={"seconds": seconds})
    for name in ["Ana", "Bea", "Cy", "Di", "Ev"]:
        rate(client, name, 5)
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE app_time SET recorded_at = now() - interval '7 days' WHERE seconds = 5400"))
        db.execute(text("UPDATE app_time SET recorded_at = now() - interval '28 days' WHERE seconds = 9000"))
        db.execute(text("UPDATE app_time SET recorded_at = now() - interval '35 days' WHERE seconds = 3601"))
        db.execute(text("UPDATE cards SET date_rated_at = now() - interval '7 days' WHERE name = 'Bea'"))
        # Five weeks back is outside the average.
        db.execute(text("UPDATE cards SET date_rated_at = now() - interval '35 days' WHERE name IN ('Cy', 'Di', 'Ev')"))

    dashboard = client.get("/dashboard").json()

    assert dashboard["this_week"] == 1.0
    assert dashboard["four_week_average"] == 0.25


def test_with_no_time_recorded_there_is_no_rate_this_week_and_no_average(client):
    rate(client, "Ana", 5)

    dashboard = client.get("/dashboard").json()

    assert dashboard["this_week"] is None
    assert dashboard["four_week_average"] is None


def test_the_funnel_counts_each_stage_reached_this_month_and_good_counts_ratings_of_4_or_5(app, client):
    ana = add(client, "Ana")
    move(client, ana, "chatting", "date_set", "dated")
    client.patch(f"/cards/{ana}", json={"date_rating": 5})
    add(client, "Bea", "chatting")
    cy = add(client, "Cy", "chatting")
    with app.state.engine.begin() as db:
        db.execute(text(f"UPDATE cards SET created_at = {LAST_MONTH}, chatting_at = {LAST_MONTH} WHERE name = 'Cy'"))
    move(client, cy, "number_swapped", "date_set")
    rate(client, "Di", 3)
    move(client, add(client, "Ev", "date_set"), "archived")
    rate(client, "Fay", 4)
    with app.state.engine.begin() as db:
        db.execute(
            text(
                f"UPDATE cards SET created_at = {LAST_MONTH}, chatting_at = {LAST_MONTH}, date_set_at = {LAST_MONTH},"
                f" dated_at = {LAST_MONTH}, date_rated_at = {LAST_MONTH} WHERE name = 'Fay'"
            )
        )

    assert client.get("/dashboard").json()["funnel"] == {
        "matched": 4,  # Ana, Bea, Di, Ev
        "chatting": 4,  # Ana, Bea, Di, Ev: Cy chatted last month
        "date_set": 4,  # Ana, Cy, Di, Ev, who stays counted once archived
        "dated": 2,  # Ana, Di
        "good": 1,  # Ana: Di rated 3, Fay was rated last month
    }


def test_ai_spend_per_good_date_and_spend_against_the_cap_come_from_this_months_recorded_costs(app, client):
    client.put("/budget", json={"cap_usd": 30})
    for name in ["Ana", "Bea", "Cy"]:
        rate(client, name, 5)
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users WHERE email = 'user@example.com'")).scalar_one()
        llm.record(db, user_id, "draft", "stub", Decimal("5.00"))
        db.execute(text(f"UPDATE llm_calls SET created_at = {LAST_MONTH}"))
        db.execute(text(f"UPDATE cards SET date_rated_at = {LAST_MONTH} WHERE name = 'Cy'"))
        llm.record(db, user_id, "draft", "stub", Decimal("8.20"))

    dashboard = client.get("/dashboard").json()

    assert dashboard["spend_per_good_date_usd"] == 4.1
    assert dashboard["budget"] == {"spend_usd": 8.2, "cap_usd": 30, "paused": False}


def test_with_no_good_date_this_month_there_is_no_spend_per_good_date(client):
    assert client.get("/dashboard").json()["spend_per_good_date_usd"] is None
