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
