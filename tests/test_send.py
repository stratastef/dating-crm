"""Tap to send: an approved draft goes out through the Tinder connector, against a stub. No live calls."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.connectors import call
from app.jobs import run_once
from app.tinder import TinderConnector
from app.vault import store_token

FIXTURES = Path(__file__).parent / "fixtures" / "tinder"
TOKEN = "tinder-session-secret"
CLEO = "5f00000000000000000000015f00000000000000000000c3"


class StubTinder:
    """Stands in for api.gotinder.com's send endpoint. `status` is what it answers; `sent` records each send."""

    def __init__(self):
        self.status = 200
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == TOKEN
        assert request.method == "POST"
        self.sent.append((request.url.path, json.loads(request.content)))
        if self.status != 200:
            return httpx.Response(self.status, json={"status": self.status})
        return httpx.Response(200, json=json.loads((FIXTURES / "send_message.json").read_text()))


@pytest.fixture
def tinder(monkeypatch):
    stub = StubTinder()
    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(stub))
    return stub


@pytest.fixture
def user_id(app, client):
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        store_token(db, user_id, "tinder", TOKEN)
    return user_id


def test_the_tinder_connector_sends_a_message_to_a_match(app, user_id, tinder):
    with app.state.engine.begin() as db:
        sent = call(db, user_id, TinderConnector(), "send", CLEO, "both. badly.")

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]
    assert sent == {"id": "64c00000000000000000c009", "sent_at": "2026-11-25T09:30:00.000Z"}


# Tap to send: the tap goes in through the API, the worker runs the job, and the result is read back through the API.


@pytest.fixture
def draft(app, client, llm, user_id) -> dict:
    """A pending reply draft on Cleo's Tinder card."""
    llm.reply = "Short, lowercase, teasing."
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    work(app)
    card_id = client.post("/cards", json={"app": "tinder", "name": "Cleo", "external_id": CLEO}).json()["id"]
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "do you climb indoors or outdoors"})
    llm.reply = "both. badly."
    return client.post(f"/cards/{card_id}/drafts").json()


def work(app) -> None:
    while run_once(app.state.engine):
        pass


def status(app, draft) -> str:
    with app.state.engine.begin() as db:
        return db.execute(text("SELECT status FROM drafts WHERE id = :id"), {"id": draft["id"]}).scalar_one()


def my_messages(client, draft) -> list[tuple]:
    rows = client.get(f"/cards/{draft['card_id']}/messages").json()
    return [(row["external_id"], row["body"]) for row in rows if row["sender"] == "me"]


def test_tapping_send_sends_the_draft_and_stores_the_message_on_the_card(app, client, draft, tinder):
    tapped = client.post(f"/drafts/{draft['id']}/send")

    assert tapped.status_code == 202
    assert tapped.json()["status"] == "approved"
    assert tinder.sent == []  # the worker sends, not the request

    work(app)

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]
    assert status(app, draft) == "sent"
    assert my_messages(client, draft) == [("64c00000000000000000c009", "both. badly.")]
    (action,) = client.get("/audit-log").json()
    assert (action["type"], action["app"], action["target"]) == ("message", "tinder", f"card:{draft['card_id']}")
    assert action["trigger"] == f"copilot: user tapped send on draft {draft['id']}"


def test_the_users_edit_is_what_gets_sent(app, client, draft, tinder):
    client.patch(f"/drafts/{draft['id']}", json={"edited": "both, badly"})

    client.post(f"/drafts/{draft['id']}/send")
    work(app)

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both, badly"})]


def test_approving_a_draft_in_the_review_queue_sends_it_once(app, client, draft, tinder):
    assert client.post(f"/drafts/{draft['id']}/approve").status_code == 200
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 409

    work(app)

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]
    assert status(app, draft) == "sent"
    assert client.get("/audit-log").json()[0]["trigger"] == f"copilot: user approved draft {draft['id']}"


def test_approving_a_draft_while_the_app_is_paused_sends_nothing(app, client, draft, tinder):
    client.post("/autopilot/pause", params={"app": "tinder"})

    assert client.post(f"/drafts/{draft['id']}/approve").status_code == 200
    work(app)

    assert tinder.sent == []
    assert status(app, draft) == "approved"


def test_a_second_tap_is_refused_and_the_draft_is_sent_once(app, client, draft, tinder):
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 202
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 409
    work(app)
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 409

    work(app)

    assert len(tinder.sent) == 1


def test_a_send_job_that_dies_after_sending_is_not_sent_again_on_retry(app, client, draft, tinder, monkeypatch):
    def crash(*args, **kwargs):
        raise RuntimeError("worker died")

    with monkeypatch.context() as patch:
        patch.setattr("app.send.record_action", crash)
        client.post(f"/drafts/{draft['id']}/send")
        work(app)
    assert len(tinder.sent) == 1
    assert status(app, draft) == "sending"

    while run_once(app.state.engine, now=datetime.now(UTC) + timedelta(hours=1)):  # the retry is due
        pass

    assert len(tinder.sent) == 1
    assert status(app, draft) == "failed"


def test_a_send_tinder_rejects_fails_the_draft_and_is_not_retried(app, client, draft, tinder):
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")

    work(app)
    while run_once(app.state.engine, now=datetime.now(UTC) + timedelta(hours=1)):
        pass

    assert len(tinder.sent) == 1
    assert status(app, draft) == "failed"
    assert my_messages(client, draft) == []
    assert client.get("/audit-log").json() == []


@pytest.mark.parametrize("scope", [{}, {"app": "tinder"}])
def test_send_is_refused_while_the_app_is_paused(app, client, draft, tinder, scope):
    client.post("/autopilot/pause", params=scope)

    refused = client.post(f"/drafts/{draft['id']}/send")

    assert refused.status_code == 409
    assert "paused" in refused.json()["detail"]
    work(app)
    assert tinder.sent == []
    assert status(app, draft) == "pending"


def test_send_is_refused_while_the_send_capability_is_off(app, client, draft, tinder, monkeypatch):
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send")

    refused = client.post(f"/drafts/{draft['id']}/send")

    assert refused.status_code == 409
    assert "tinder:send is disabled" in refused.json()["detail"]
    work(app)
    assert tinder.sent == []
    assert status(app, draft) == "pending"


def test_a_pause_after_the_tap_stops_the_send_and_the_draft_can_be_tapped_again(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")
    client.post("/autopilot/pause", params={"app": "tinder"})

    work(app)

    assert tinder.sent == []
    assert status(app, draft) == "pending"


def test_send_needs_the_users_own_draft_on_a_card_linked_to_a_match(app, client, client_for, draft, tinder, llm):
    other = client_for("bob@example.com")
    unlinked = client.post("/cards", json={"app": "tinder", "name": "Typed in by hand"}).json()["id"]
    by_hand = client.post(f"/cards/{unlinked}/drafts").json()

    assert other.post(f"/drafts/{draft['id']}/send").status_code == 404
    assert client.post(f"/drafts/{by_hand['id']}/send").status_code == 409
    work(app)
    assert tinder.sent == []
