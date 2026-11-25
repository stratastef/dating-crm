from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import calendar

SEVEN = datetime(2026, 12, 1, 19, tzinfo=UTC)
NINE = SEVEN + timedelta(hours=2)
ELEVEN = SEVEN + timedelta(hours=4)


def connect(client, app) -> None:
    """Run the OAuth flow as Google's redirect would: the browser returns with a code and the state."""
    state = parse_qs(urlparse(client.get("/calendar/connect").json()["url"]).query)["state"][0]
    assert TestClient(app).get("/calendar/callback", params={"code": "the-code", "state": state}).status_code == 200


@pytest.fixture
def user(client, app):
    """The connected user's ID and a function that creates one of their cards."""
    connect(client, app)
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()

    def card(name: str) -> int:
        return client.post("/cards", json={"app": "tinder", "name": name}).json()["id"]

    return user_id, card


def run(app, function, *args, **kwargs):
    """Call a calendar function in its own committed transaction, as a job handler would."""
    with app.state.engine.begin() as db:
        return function(db, *args, **kwargs)


def test_user_connects_google_calendar(client, app, gcal):
    assert client.get("/calendar").json() == {"connected": False}

    url = urlparse(client.get("/calendar/connect").json()["url"])
    query = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert query["client_id"] == ["test-client-id"]
    assert query["access_type"] == ["offline"]  # without it Google gives no refresh token

    connect(client, app)

    assert gcal.codes == ["the-code"]
    assert client.get("/calendar").json() == {"connected": True}


def test_callback_with_a_forged_state_connects_nobody(client, app, gcal):
    response = TestClient(app).get("/calendar/callback", params={"code": "the-code", "state": "forged"})

    assert response.status_code == 400
    assert gcal.codes == []
    assert client.get("/calendar").json() == {"connected": False}


def test_offered_slots_come_from_free_time_only(app, user, gcal):
    user_id, _ = user
    gcal.busy = [(NINE - timedelta(minutes=30), NINE + timedelta(minutes=30))]

    slots = run(app, calendar.free_slots, user_id, SEVEN, SEVEN + timedelta(hours=6))

    # Two-hour slots from 19:00: 19-21 and 21-23 touch the busy half hours around 21:00.
    assert slots == [(ELEVEN, ELEVEN + timedelta(hours=2))]
    assert gcal.tokens == [gcal.refresh_token]


def test_calendar_functions_need_a_connected_calendar(app, client):
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()

    with pytest.raises(calendar.NotConnected):
        run(app, calendar.free_slots, user_id, SEVEN, NINE)


def test_holding_a_slot_creates_a_tentative_event_and_an_audit_entry(app, client, user, gcal):
    user_id, card = user
    ada = card("Ada")

    run(app, calendar.hold_slot, user_id, ada, SEVEN, NINE, trigger="chat autopilot: proposed a time")

    assert [(e["status"], e["start"], e["end"]) for e in gcal.events.values()] == [("tentative", SEVEN, NINE)]
    assert run(app, calendar.free_slots, user_id, SEVEN, ELEVEN) == [(NINE, ELEVEN)]
    (entry,) = client.get("/audit-log", params={"type": "calendar_hold"}).json()
    assert entry["app"] == "tinder"
    assert entry["target"] == f"card:{ada} hold {SEVEN.isoformat()}"
    assert entry["trigger"] == "chat autopilot: proposed a time"


def test_a_slot_busy_in_google_cannot_be_held(app, user, gcal):
    user_id, card = user
    gcal.busy = [(SEVEN, NINE)]

    with pytest.raises(calendar.SlotTaken):
        run(app, calendar.hold_slot, user_id, card("Ada"), SEVEN, NINE, trigger="test")

    assert gcal.events == {}


def test_two_matches_never_get_the_same_slot(app, user, gcal):
    user_id, card = user
    run(app, calendar.hold_slot, user_id, card("Ada"), SEVEN, NINE, trigger="test")

    with pytest.raises(calendar.SlotTaken):
        # Overlaps the last hour of Ada's slot.
        run(app, calendar.hold_slot, user_id, card("Grace"), SEVEN + timedelta(hours=1), ELEVEN, trigger="test")

    assert len(gcal.events) == 1


def test_the_database_itself_rejects_overlapping_holds(app, user):
    user_id, card = user
    insert = text(
        "INSERT INTO calendar_holds (user_id, card_id, slot)"
        " VALUES (:user_id, :card_id, tstzrange(:start, :end))"
    )
    with app.state.engine.begin() as db:
        db.execute(insert, {"user_id": user_id, "card_id": card("Ada"), "start": SEVEN, "end": NINE})

    with pytest.raises(IntegrityError), app.state.engine.begin() as db:
        db.execute(insert, {"user_id": user_id, "card_id": card("Grace"), "start": SEVEN, "end": NINE})


def test_declining_releases_the_cards_holds(app, client, user, gcal):
    user_id, card = user
    ada, grace = card("Ada"), card("Grace")
    run(app, calendar.hold_slot, user_id, ada, SEVEN, NINE, trigger="test")
    run(app, calendar.hold_slot, user_id, grace, NINE, ELEVEN, trigger="test")

    run(app, calendar.release_holds, user_id, ada, trigger="match declined")

    assert [e["start"] for e in gcal.events.values()] == [NINE]  # Grace's hold stays
    assert run(app, calendar.free_slots, user_id, SEVEN, ELEVEN) == [(SEVEN, NINE)]
    newest = client.get("/audit-log", params={"type": "calendar_hold"}).json()[0]
    assert (newest["target"], newest["trigger"]) == (f"card:{ada} release {SEVEN.isoformat()}", "match declined")


def test_archiving_a_card_releases_its_holds(app, client, user, gcal):
    user_id, card = user
    ada = card("Ada")
    run(app, calendar.hold_slot, user_id, ada, SEVEN, NINE, trigger="test")

    assert client.patch(f"/cards/{ada}", json={"stage": "archived"}).status_code == 200

    assert gcal.events == {}
    assert run(app, calendar.free_slots, user_id, SEVEN, NINE) == [(SEVEN, NINE)]


def test_reaching_date_set_turns_the_hold_into_an_event(app, client, user, gcal):
    user_id, card = user
    ada = card("Ada")
    run(app, calendar.hold_slot, user_id, ada, SEVEN, NINE, trigger="test")

    assert client.patch(f"/cards/{ada}", json={"stage": "date_set"}).status_code == 200

    assert [(e["status"], e["summary"]) for e in gcal.events.values()] == [("confirmed", "Date with Ada")]
    # The date keeps its slot: no other match can be offered it, and archiving later does not delete the event.
    assert run(app, calendar.free_slots, user_id, SEVEN, NINE) == []
    client.patch(f"/cards/{ada}", json={"stage": "archived"})
    assert len(gcal.events) == 1


def test_confirming_one_of_several_holds_releases_the_others(app, user, gcal):
    user_id, card = user
    ada = card("Ada")
    run(app, calendar.hold_slot, user_id, ada, SEVEN, NINE, trigger="test")
    run(app, calendar.hold_slot, user_id, ada, NINE, ELEVEN, trigger="test")

    assert run(app, calendar.confirm_date, user_id, ada, trigger="match agreed", start=NINE) is True

    assert [(e["status"], e["start"]) for e in gcal.events.values()] == [("confirmed", NINE)]
    assert run(app, calendar.free_slots, user_id, SEVEN, ELEVEN) == [(SEVEN, NINE)]
