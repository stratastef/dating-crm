"""The status strip: `GET /status` lists what stops autopilot, in the order the phone shows it."""

from datetime import UTC, datetime

import httpx
import pytest

from app.jobs import run_once
from app.tinder import TinderConnector


@pytest.fixture
def tinder_refuses(monkeypatch):
    """Tinder answers every request with 401: the next sync stores an alert and pauses Tinder."""
    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(lambda request: httpx.Response(401)))


def break_tinder(client, app):
    client.put("/connectors/tinder/token", json={"token": "expired-session"})  # queues a sync
    while run_once(app.state.engine):
        pass


def test_nothing_paused_no_budget_reached_and_no_connector_alert_gives_an_empty_strip(client):
    assert client.get("/status").json() == []


def test_the_pause_on_all_apps_comes_before_each_paused_app(client):
    client.post("/autopilot/pause", params={"app": "tinder"})
    client.post("/autopilot/pause")
    client.post("/autopilot/pause", params={"app": "hinge"})

    assert client.get("/status").json() == [
        {"kind": "paused", "app": None, "resets_at": None},
        {"kind": "paused", "app": "hinge", "resets_at": None},
        {"kind": "paused", "app": "tinder", "resets_at": None},
    ]


def test_resume_takes_the_pause_off_the_strip(client, client_for):
    client.post("/autopilot/pause")
    client.post("/autopilot/pause", params={"app": "tinder"})
    client_for("other@example.com").post("/autopilot/pause")  # another user's pause is not on this strip

    client.post("/autopilot/resume", params={"app": "tinder"})
    client.post("/autopilot/resume")

    assert client.get("/status").json() == []


def test_a_reached_ai_budget_says_when_the_new_month_resets_it(client, monkeypatch):
    monkeypatch.setattr("app.status.now", lambda: datetime(2026, 12, 15, 9, 30, tzinfo=UTC))
    client.put("/budget", json={"cap_usd": 0})  # nothing spent is already at a cap of 0

    assert client.get("/status").json() == [{"kind": "budget_reached", "app": None, "resets_at": "2027-01-01T00:00:00Z"}]

    client.put("/budget", json={"cap_usd": 30})
    assert client.get("/status").json() == []


def test_a_connector_alert_names_its_app_until_the_user_answers_it(client, app, tinder_refuses):
    break_tinder(client, app)
    client.post("/autopilot/resume", params={"app": "tinder"})  # the alert outlives the pause it caused

    assert client.get("/status").json() == [{"kind": "connector_alert", "app": "tinder", "resets_at": None}]

    client.put("/connectors/tinder/copilot-only")
    assert client.get("/status").json() == []


def test_messages_come_as_all_apps_pause_then_app_pauses_then_budget_then_connector_alerts(client, app, tinder_refuses):
    client.put("/budget", json={"cap_usd": 0})
    break_tinder(client, app)  # also pauses Tinder
    client.post("/autopilot/pause", params={"app": "hinge"})
    client.post("/autopilot/pause")

    assert [(message["kind"], message["app"]) for message in client.get("/status").json()] == [
        ("paused", None),
        ("paused", "hinge"),
        ("paused", "tinder"),
        ("budget_reached", None),
        ("connector_alert", "tinder"),
    ]
