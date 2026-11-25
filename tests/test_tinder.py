"""Tinder connector and sync, against the hand-written fixtures in `tests/fixtures/tinder`. No live calls."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.connectors import alerts, call
from app.jobs import run_once
from app.sync import SYNC_INTERVAL
from app.tinder import TinderConnector
from app.vault import read_token, store_token

FIXTURES = Path(__file__).parent / "fixtures" / "tinder"
TOKEN = "tinder-session-secret"
ME = "5f0000000000000000000001"
ANA, BEA, CLEO = (ME + person for person in ("5f00000000000000000000a1", "5f00000000000000000000b2", "5f00000000000000000000c3"))


class StubTinder:
    """Stands in for api.gotinder.com. Set `later = True` to serve the state of the account some days on."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.later = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("X-Auth-Token") != TOKEN:
            return self._fixture("unauthorized", 401)
        prefix = "later_" if self.later else ""
        path, query = request.url.path, request.url.params
        if path == "/v2/matches" and query["message"] == "0":
            if self.later:
                return self._fixture("later_matches_new")
            return self._fixture("matches_new_page2" if query.get("page_token") == "bmV4dA==" else "matches_new_page1")
        if path == "/v2/matches" and query["message"] == "1":
            return self._fixture(prefix + "matches_messaged")
        if path == f"/v2/matches/{CLEO}/messages":
            return self._fixture(prefix + "messages_cleo")
        if path == f"/v2/matches/{BEA}/messages" and self.later:
            return self._fixture("later_messages_bea")
        return httpx.Response(404, json={"meta": {"status": 404}})

    def _fixture(self, name: str, status: int = 200) -> httpx.Response:
        return httpx.Response(status, json=json.loads((FIXTURES / f"{name}.json").read_text()))

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]


@pytest.fixture
def tinder(monkeypatch):
    stub = StubTinder()
    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(stub))
    return stub


@pytest.fixture
def db(app, client):
    with app.state.engine.begin() as connection:
        yield connection


@pytest.fixture
def user_id(db):
    user_id = db.execute(text("SELECT id FROM users")).scalar_one()
    store_token(db, user_id, "tinder", TOKEN)
    return user_id


def test_read_matches_returns_every_match_on_every_page(db, user_id, tinder):
    matches = call(db, user_id, TinderConnector(), "read_matches")

    assert matches == [
        {"id": ANA, "name": "Ana", "has_messages": False, "last_message_id": None},
        {"id": BEA, "name": "Bea", "has_messages": False, "last_message_id": None},
        {"id": CLEO, "name": "Cleo", "has_messages": True, "last_message_id": "64c00000000000000000c002"},
    ]
    assert {request.headers["X-Auth-Token"] for request in tinder.requests} == {TOKEN}


def test_read_messages_tells_my_messages_from_theirs(db, user_id, tinder):
    messages = call(db, user_id, TinderConnector(), "read_messages", CLEO)

    assert messages == [
        {
            "id": "64c00000000000000000c002",
            "sender": "me",
            "body": "Hey Cleo, good thanks. You?",
            "sent_at": "2026-11-20T18:05:00.000Z",
        },
        {
            "id": "64c00000000000000000c001",
            "sender": "them",
            "body": "Hi! How was your weekend?",
            "sent_at": "2026-11-20T18:00:00.000Z",
        },
    ]


# Sync: the token goes in through the API, the worker runs the job, and the result is read back through /cards.


def submit_token(client, token=TOKEN):
    return client.put("/connectors/tinder/token", json={"token": token})


def cards(client) -> dict[str, dict]:
    return {card["name"]: card for card in client.get("/cards", params={"app": "tinder"}).json()}


def messages(client, card) -> list[tuple]:
    rows = client.get(f"/cards/{card['id']}/messages").json()
    return [(row["external_id"], row["sender"], row["body"]) for row in rows]


def sync_again(app):
    assert run_once(app.state.engine, now=datetime.now(UTC) + SYNC_INTERVAL) is True


def test_the_submitted_token_is_stored_in_the_vault_and_not_echoed(client, app):
    response = submit_token(client)

    assert response.status_code == 204
    assert TOKEN not in response.text
    with app.state.engine.begin() as db:
        assert read_token(db, db.execute(text("SELECT id FROM users")).scalar_one(), "tinder") == TOKEN
        assert TOKEN not in db.execute(text("SELECT string_agg(j::text, ' ') FROM jobs j")).scalar_one()


def test_a_token_for_an_app_without_a_connector_is_refused(client):
    assert client.put("/connectors/grindr/token", json={"token": "x"}).status_code == 404


def test_first_sync_puts_new_matches_in_matched_and_matches_with_messages_in_chatting(client, app, tinder):
    submit_token(client)

    assert run_once(app.state.engine) is True

    synced = cards(client)
    assert {name: (card["external_id"], card["stage"]) for name, card in synced.items()} == {
        "Ana": (ANA, "matched"),
        "Bea": (BEA, "matched"),
        "Cleo": (CLEO, "chatting"),
    }
    assert messages(client, synced["Cleo"]) == [
        ("64c00000000000000000c001", "them", "Hi! How was your weekend?"),
        ("64c00000000000000000c002", "me", "Hey Cleo, good thanks. You?"),
    ]
    assert messages(client, synced["Ana"]) == []


def test_a_later_sync_adds_what_is_new_without_duplicates(client, app, tinder):
    submit_token(client)
    run_once(app.state.engine)
    tinder.later = True

    sync_again(app)

    synced = cards(client)
    assert {name: card["stage"] for name, card in synced.items()} == {
        "Ana": "matched",
        "Bea": "chatting",  # she wrote first
        "Cleo": "chatting",
    }
    assert messages(client, synced["Bea"]) == [("64b00000000000000000b001", "them", "Hello there")]
    assert messages(client, synced["Cleo"]) == [
        ("64c00000000000000000c001", "them", "Hi! How was your weekend?"),
        ("64c00000000000000000c002", "me", "Hey Cleo, good thanks. You?"),
        ("64c00000000000000000c003", "them", "All good. Coffee on Friday?"),
    ]


def test_sync_keeps_the_stage_and_notes_the_user_set(client, app, tinder):
    submit_token(client)
    run_once(app.state.engine)
    before = cards(client)
    client.patch(f"/cards/{before['Cleo']['id']}", json={"stage": "number_swapped", "notes": "likes climbing"})
    client.patch(f"/cards/{before['Ana']['id']}", json={"stage": "archived"})
    tinder.later = True

    sync_again(app)

    after = cards(client)
    assert (after["Cleo"]["stage"], after["Cleo"]["notes"]) == ("number_swapped", "likes climbing")
    assert after["Ana"]["stage"] == "archived"


def test_messages_are_fetched_only_for_matches_with_a_new_message(client, app, tinder):
    submit_token(client)
    run_once(app.state.engine)
    assert tinder.paths().count(f"/v2/matches/{CLEO}/messages") == 1

    sync_again(app)  # nothing changed on Tinder

    assert [path for path in tinder.paths() if path.endswith("/messages")] == [f"/v2/matches/{CLEO}/messages"]


def test_sync_runs_again_on_a_schedule_and_only_once_per_interval(client, app, tinder):
    submit_token(client)
    submit_token(client)  # a second submit must not start a second schedule
    while run_once(app.state.engine):
        pass
    soon = datetime.now(UTC) + SYNC_INTERVAL - timedelta(minutes=1)
    assert run_once(app.state.engine, now=soon) is False
    requests_so_far = len(tinder.requests)

    due = datetime.now(UTC) + SYNC_INTERVAL
    assert run_once(app.state.engine, now=due) is True
    assert run_once(app.state.engine, now=due) is False
    assert len(tinder.requests) > requests_so_far


def test_each_user_gets_only_their_own_matches(client_for, app, tinder):
    alice, bob = client_for("alice@example.com"), client_for("bob@example.com")
    submit_token(alice)

    run_once(app.state.engine)

    assert len(cards(alice)) == 3
    assert cards(bob) == {}


def test_a_rejected_token_falls_back_to_copilot_without_leaking_the_token(client, app, tinder, caplog):
    caplog.set_level(logging.DEBUG)
    submit_token(client, "expired-session-secret")

    run_once(app.state.engine)

    assert cards(client) == {}
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        [alert] = alerts(db, user_id)
        stored = db.execute(text("SELECT string_agg(j::text, ' ') FROM jobs j")).scalar_one()
    assert (alert.app, alert.capability) == ("tinder", "read_matches")
    assert "401" in alert.error
    assert "expired-session-secret" not in alert.error + stored + caplog.text


def test_submitting_a_fresh_token_turns_the_connector_back_on(client, app, tinder):
    submit_token(client, "expired-session-secret")
    run_once(app.state.engine)

    submit_token(client)
    run_once(app.state.engine)

    assert len(cards(client)) == 3
