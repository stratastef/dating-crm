"""Tap to send: an approved draft goes out through the Tinder connector, against a stub. No live calls."""

import json
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from sqlalchemy import text

from app.connectors import call
from app.jobs import run_once
from app.send import UNDO_WINDOW
from app.tinder import TinderConnector
from app.vault import store_token
from tests.test_drafts import drafted

FIXTURES = Path(__file__).parent / "fixtures" / "tinder"
TOKEN = "tinder-session-secret"
CLEO = "5f00000000000000000000015f00000000000000000000c3"


class StubTinder:
    """Stands in for api.gotinder.com's send endpoint. `status` is what it answers; `sent` records each send.
    `during_send`, when set, runs while a send is under way."""

    def __init__(self):
        self.status = 200
        self.sent: list[tuple[str, dict]] = []
        self.during_send: Callable[[], object] | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == TOKEN
        assert request.method == "POST"
        self.sent.append((request.url.path, json.loads(request.content)))
        if self.during_send:
            self.during_send()
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
    llm.reply = drafted("both. badly.")
    return client.post(f"/cards/{card_id}/drafts").json()


def work(app) -> None:
    """Run every job that is due once a user's Send is past its undo window."""
    while run_once(app.state.engine, now=datetime.now(UTC) + UNDO_WINDOW):
        pass


def work_now(app) -> None:
    """Run every job that is due now."""
    while run_once(app.state.engine):
        pass


def work_after_send_time(app) -> None:
    """Run every job that is due once autopilot's planned sends are: at most 12 hours out, plus the night window."""
    while run_once(app.state.engine, now=datetime.now(UTC) + timedelta(days=1)):
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


def test_a_users_send_waits_five_seconds_for_undo_before_it_goes_out(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")

    work_now(app)
    assert tinder.sent == []

    work(app)
    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]


def kinds(client) -> list[str]:
    return [item["kind"] for item in client.get("/queue").json()]


def test_undo_inside_the_five_seconds_returns_the_draft_to_pending_and_nothing_is_sent(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")

    undone = client.post(f"/drafts/{draft['id']}/undo-send")

    assert undone.status_code == 200
    assert undone.json()["status"] == "pending"
    work(app)
    assert tinder.sent == []
    assert kinds(client) == ["draft"]


def test_a_send_tapped_again_after_undo_waits_its_own_undo_window(app, client, draft, tinder, monkeypatch):
    client.post(f"/drafts/{draft['id']}/send")
    client.post(f"/drafts/{draft['id']}/undo-send")
    monkeypatch.setattr("app.send.UNDO_WINDOW", timedelta(hours=1))
    client.post(f"/drafts/{draft['id']}/send")

    work(app)  # the first send's time has come, the second's has not

    assert tinder.sent == []


def test_undo_after_the_send_job_started_is_refused_and_the_message_goes_out_once(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")
    undos = []
    tinder.during_send = lambda: undos.append(client.post(f"/drafts/{draft['id']}/undo-send"))

    work(app)

    assert [undo.status_code for undo in undos] == [409]
    assert undos[0].json()["detail"] == "the draft is sending"
    assert client.post(f"/drafts/{draft['id']}/undo-send").status_code == 409
    work(app)
    assert len(tinder.sent) == 1


def test_only_the_users_own_draft_can_be_undone(client, client_for, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")

    assert client_for("bob@example.com").post(f"/drafts/{draft['id']}/undo-send").status_code == 404


def test_a_failed_send_waits_in_the_review_queue_as_failed_send(app, client, draft, tinder):
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")

    work(app)

    (item,) = client.get("/queue").json()
    assert item["kind"] == "failed_send"
    assert (item["draft"]["id"], item["draft"]["status"]) == (draft["id"], "failed")
    assert item["card"]["reason"] == "failed_send"
    assert item["message"]["body"] == "do you climb indoors or outdoors"


def test_a_cards_draft_list_holds_its_pending_copied_and_failed_drafts_newest_first(app, client, draft, tinder):
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)
    card_id = draft["card_id"]
    copied = client.post(f"/cards/{card_id}/drafts").json()["id"]
    client.post(f"/drafts/{copied}/copy")
    dismissed = client.post(f"/cards/{card_id}/drafts").json()["id"]
    client.post(f"/drafts/{dismissed}/dismiss")
    pending = client.post(f"/cards/{card_id}/drafts").json()["id"]

    listed = client.get(f"/cards/{card_id}").json()["drafts"]

    assert [(listed["id"], listed["status"]) for listed in listed] == [
        (pending, "pending"),
        (copied, "copied"),
        (draft["id"], "failed"),
    ]


def test_retry_sends_a_failed_draft_through_the_same_gate(app, client, draft, tinder, monkeypatch):
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)
    assert kinds(client) == ["failed_send"]
    tinder.status = 200

    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send")
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 409  # the gate holds for a retry too
    monkeypatch.delenv("CONNECTOR_DISABLED_CAPABILITIES")
    retried = client.post(f"/drafts/{draft['id']}/send")

    assert retried.status_code == 202
    assert retried.json()["status"] == "approved"
    work(app)
    assert len(tinder.sent) == 2  # the failed attempt and the retry
    assert my_messages(client, draft) == [("64c00000000000000000c009", "both. badly.")]
    assert kinds(client) == []


def test_the_users_edit_is_what_gets_sent(app, client, draft, tinder):
    client.patch(f"/drafts/{draft['id']}", json={"edited": "both, badly"})

    client.post(f"/drafts/{draft['id']}/send")
    work(app)

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both, badly"})]


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
def test_a_pause_stops_autopilot_only_so_the_users_tap_still_sends(app, client, draft, tinder, scope):
    client.post("/autopilot/pause", params=scope)

    assert client.post(f"/drafts/{draft['id']}/send").status_code == 202
    work(app)

    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]
    assert status(app, draft) == "sent"


def test_send_is_refused_while_the_send_capability_is_off(app, client, draft, tinder, monkeypatch):
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send")

    refused = client.post(f"/drafts/{draft['id']}/send")

    assert refused.status_code == 409
    assert "tinder:send is disabled" in refused.json()["detail"]
    work(app)
    assert tinder.sent == []
    assert status(app, draft) == "pending"


def test_marking_an_app_copilot_only_makes_its_drafts_not_sendable(app, client, draft, tinder):
    client.put("/connectors/tinder/copilot-only")

    refused = client.post(f"/drafts/{draft['id']}/send")

    assert refused.status_code == 409
    assert "tinder is copilot-only" in refused.json()["detail"]
    work(app)
    assert tinder.sent == []
    assert status(app, draft) == "pending"


def test_a_pause_after_the_tap_does_not_stop_the_send(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send")
    client.post("/autopilot/pause", params={"app": "tinder"})

    work(app)

    assert len(tinder.sent) == 1
    assert status(app, draft) == "sent"


def test_a_capability_switched_off_after_the_tap_stops_the_send_and_the_draft_can_be_tapped_again(
    app, client, draft, tinder, monkeypatch
):
    client.post(f"/drafts/{draft['id']}/send")
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send")

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


# Send at a chosen time: the user's own draft goes out when they say, and Unschedule takes it back.


def work_at(app, at: datetime) -> None:
    """Run every job that is due at `at`."""
    while run_once(app.state.engine, now=at):
        pass


def test_a_send_at_a_chosen_time_goes_out_at_that_time_not_before(app, client, draft, tinder):
    chosen = datetime.now(UTC) + timedelta(hours=1)

    tapped = client.post(f"/drafts/{draft['id']}/send", json={"send_at": chosen.isoformat()})

    assert tapped.status_code == 202
    assert tapped.json()["status"] == "approved"
    work_at(app, chosen - timedelta(minutes=1))
    assert tinder.sent == []
    work_at(app, chosen)
    assert tinder.sent == [(f"/user/matches/{CLEO}", {"message": "both. badly."})]


def test_the_five_second_undo_wait_applies_only_to_sends_without_a_time(app, client, draft, tinder):
    client.post(f"/drafts/{draft['id']}/send", json={"send_at": datetime.now(UTC).isoformat()})

    work_now(app)

    assert len(tinder.sent) == 1


def test_the_users_chosen_send_time_is_used_as_given_even_in_the_night_window_past_twelve_hours(
    app, client, draft, tinder
):
    zone = ZoneInfo("Europe/Berlin")
    client.patch("/settings", json={"time_zone": "Europe/Berlin"})  # night window 01:00 to 07:00
    chosen = datetime.combine(datetime.now(zone).date() + timedelta(days=2), time(3, 0), zone)

    tapped = client.post(f"/drafts/{draft['id']}/send", json={"send_at": chosen.isoformat()})

    assert datetime.fromisoformat(tapped.json()["send_at"]) == chosen
    work_at(app, chosen)
    assert len(tinder.sent) == 1


def test_unschedule_cancels_a_scheduled_send_and_the_draft_is_pending_again(app, client, draft, tinder):
    chosen = datetime.now(UTC) + timedelta(hours=1)
    client.post(f"/drafts/{draft['id']}/send", json={"send_at": chosen.isoformat()})

    unscheduled = client.post(f"/drafts/{draft['id']}/unschedule")

    assert unscheduled.status_code == 200
    assert unscheduled.json()["status"] == "pending"
    work_at(app, chosen)
    assert tinder.sent == []
    assert kinds(client) == ["draft"]
    assert client.post(f"/drafts/{draft['id']}/unschedule").status_code == 409


def test_a_scheduled_send_shows_on_the_card_which_then_waits_for_them_not_for_you(app, client, draft, tinder):
    chosen = datetime.now(UTC) + timedelta(hours=1)

    client.post(f"/drafts/{draft['id']}/send", json={"send_at": chosen.isoformat()})

    card = client.get(f"/cards/{draft['card_id']}").json()
    scheduled = card["scheduled_send"]
    assert (scheduled["id"], scheduled["status"], datetime.fromisoformat(scheduled["send_at"])) == (
        draft["id"],
        "approved",
        chosen,
    )
    assert (card["pipeline_group"], card["reason"], card["planned_send"]) == ("waiting_for_them", None, None)
    client.post(f"/drafts/{draft['id']}/send")  # refused: it is scheduled already
    assert client.get(f"/cards/{draft['card_id']}").json()["scheduled_send"]["id"] == draft["id"]
