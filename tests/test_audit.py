import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit import record_action


@pytest.fixture
def record(app):
    """`record("user@example.com", type=..., ...)` records an action the way the worker does."""

    def record(email: str, **action) -> None:
        with app.state.engine.begin() as connection:
            user_id = connection.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar_one()
            record_action(connection, user_id, **action)

    return record


def test_a_recorded_action_appears_in_the_users_log(client, record):
    record("user@example.com", type="message", app="tinder", target="match:42", trigger="chat autopilot: reply due")

    response = client.get("/audit-log")

    assert response.status_code == 200
    [entry] = response.json()
    assert entry["type"] == "message"
    assert entry["app"] == "tinder"
    assert entry["target"] == "match:42"
    assert entry["trigger"] == "chat autopilot: reply due"
    assert entry["created_at"]


def test_log_is_newest_first_and_filters_by_app_and_type(client, record):
    record("user@example.com", type="like", app="tinder", target="profile:1", trigger="swipe autopilot")
    record("user@example.com", type="pass", app="hinge", target="profile:2", trigger="swipe autopilot")
    record("user@example.com", type="like", app="hinge", target="profile:3", trigger="swipe autopilot")

    def targets(**params):
        return [entry["target"] for entry in client.get("/audit-log", params=params).json()]

    assert targets() == ["profile:3", "profile:2", "profile:1"]
    assert targets(app="hinge") == ["profile:3", "profile:2"]
    assert targets(type="like") == ["profile:3", "profile:1"]
    assert targets(app="hinge", type="like") == ["profile:3"]


def test_log_lists_only_the_current_users_entries(client_for, record):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    record("alice@example.com", type="message", app="tinder", target="match:1", trigger="chat autopilot")

    assert len(alice.get("/audit-log").json()) == 1
    assert bob.get("/audit-log").json() == []


def test_log_requires_authentication(app):
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/audit-log").status_code == 401


def test_an_unknown_action_type_is_not_recorded(client, record):
    with pytest.raises(DBAPIError):
        record("user@example.com", type="superlike", app="tinder", target="profile:1", trigger="swipe autopilot")

    assert client.get("/audit-log").json() == []


@pytest.mark.parametrize("statement", ["UPDATE audit_log SET trigger = 'edited'", "DELETE FROM audit_log"])
def test_entries_cannot_be_changed_or_removed(app, client, record, statement):
    record("user@example.com", type="message", app="tinder", target="match:42", trigger="chat autopilot")

    with pytest.raises(DBAPIError, match="append-only"):
        with app.state.engine.begin() as connection:
            connection.execute(text(statement))

    [entry] = client.get("/audit-log").json()
    assert entry["trigger"] == "chat autopilot"


def test_deleting_a_user_still_removes_their_log(app, client, record):
    record("user@example.com", type="message", app="tinder", target="match:42", trigger="chat autopilot")

    with app.state.engine.begin() as connection:
        connection.execute(text("DELETE FROM users"))
        assert connection.execute(text("SELECT count(*) FROM audit_log")).scalar_one() == 0


def test_an_entry_about_a_person_shows_their_current_name_and_one_about_the_user_none(app, client, record):
    """The log never stores a name: the activity log reads it from the card or swipe candidate."""
    card_id = client.post("/cards", json={"app": "tinder", "name": "Ada"}).json()["id"]
    with app.state.engine.begin() as connection:
        candidate_id = connection.execute(
            text(
                "INSERT INTO swipe_candidates (user_id, app, profile_id, name, bio, photos, suggestion, reason, source)"
                " SELECT id, 'tinder', 'p1', 'Bea', '', '[]', 'like', '', 'model' FROM users RETURNING id"
            )
        ).scalar_one()
    record("user@example.com", type="message", app="tinder", target=f"card:{card_id}", trigger="copilot")
    record("user@example.com", type="calendar_hold", app="tinder", target=f"card:{card_id} hold 2026-12-01", trigger="x")
    record("user@example.com", type="like", app="tinder", target=f"candidate:{candidate_id}", trigger="swipe")
    record("user@example.com", type="profile_change", app="tinder", target="bio", trigger="copilot")
    client.patch(f"/cards/{card_id}", json={"name": "Ada L."})

    names = [entry["name"] for entry in client.get("/audit-log").json()]

    assert names == [None, "Bea", "Ada L.", "Ada L."]
