from datetime import UTC, datetime, timedelta

from sqlalchemy import text


def this_monday() -> str:
    today = datetime.now(UTC).date()
    return (today - timedelta(days=today.weekday())).isoformat()


def rate(client, name: str, rating: int) -> None:
    card_id = client.post("/cards", json={"app": "tinder", "name": name, "stage": "dated"}).json()["id"]
    client.patch(f"/cards/{card_id}", json={"date_rating": rating})


def test_time_the_app_reports_is_recorded_and_summed_for_the_week(client):
    assert client.post("/time", json={"seconds": 1800}).status_code == 204
    client.post("/time", json={"seconds": 5400})

    assert client.get("/dashboard").json() == [
        {"week": this_monday(), "good_dates": 0, "hours": 2.0, "good_dates_per_hour": 0.0}
    ]


def test_reported_time_must_be_between_one_second_and_one_day(client):
    assert client.post("/time", json={"seconds": 0}).status_code == 422
    assert client.post("/time", json={"seconds": 86401}).status_code == 422


def test_good_dates_per_hour_counts_only_ratings_of_4_or_5(client):
    client.post("/time", json={"seconds": 4 * 3600})
    for name, rating in [("Ana", 5), ("Bea", 4), ("Cy", 3), ("Di", 1)]:
        rate(client, name, rating)

    assert client.get("/dashboard").json() == [
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

    assert client.get("/dashboard").json() == [
        {"week": "2026-11-02", "good_dates": 1, "hours": 1.0, "good_dates_per_hour": 1.0},
        {"week": "2026-11-09", "good_dates": 1, "hours": 2.0, "good_dates_per_hour": 0.5},
    ]


def test_a_week_with_good_dates_and_no_recorded_time_has_no_rate(client):
    rate(client, "Ana", 5)

    assert client.get("/dashboard").json() == [
        {"week": this_monday(), "good_dates": 1, "hours": 0.0, "good_dates_per_hour": None}
    ]


def test_a_date_stays_in_the_week_it_was_first_rated(app, client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Ana", "stage": "dated"}).json()["id"]
    client.patch(f"/cards/{card_id}", json={"date_rating": 5})
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE cards SET date_rated_at = '2026-11-03 12:00+00'"))

    client.patch(f"/cards/{card_id}", json={"date_rating": 4, "notes": "saved again"})

    assert [week["week"] for week in client.get("/dashboard").json()] == ["2026-11-02"]


def test_the_dashboard_shows_only_the_callers_time_and_dates(client_for):
    alice = client_for("alice@example.com")
    alice.post("/time", json={"seconds": 3600})
    rate(alice, "Ana", 5)

    assert client_for("bob@example.com").get("/dashboard").json() == []
