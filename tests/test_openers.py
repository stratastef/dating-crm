"""Openers (ADR 0008, user story 143): chat autopilot writes an opener to each new match and plans it for a random
time 30 minutes to 6 hours after the match synced, outside the night window and at least 10 minutes from the
user's other openers.

New matches sync from a Tinder stub, the worker runs, and the planned sends are read from the card summaries.
"""

import json
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import httpx
import pytest

from app.jobs import run_once
from app.tinder import TinderConnector
from tests.test_drafts import drafted, write_profile
from tests.test_pipeline import placed
from tests.test_send import TOKEN, work_after_send_time, work_now
from tests.test_send_timing import at_local_hour, send_at

OPENER = "biscuit looks like he runs the house"


class StubTinder:
    """Stands in for api.gotinder.com: `names` are the account's matches, all new and with no messages yet.
    `sent` records each message sent."""

    def __init__(self):
        self.names: list[str] = []
        self.sent: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Auth-Token"] == TOKEN
        if request.method == "POST":
            self.sent.append(json.loads(request.content)["message"])
            return httpx.Response(200, json={"_id": f"sent-{len(self.sent)}", "sent_date": datetime.now(UTC).isoformat()})
        new = request.url.params.get("message") == "0"  # the web client lists matches without messages apart
        matches = [{"_id": f"match-{name}", "person": {"_id": name, "name": name}} for name in self.names if new]
        return httpx.Response(200, json={"data": {"matches": matches}})


@pytest.fixture
def tinder(monkeypatch):
    stub = StubTinder()
    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(stub))
    return stub


@pytest.fixture
def autopilot(app, client, llm):
    """A user with a style profile and chat autopilot on, the AI disclosure off."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.put("/autonomy/chat", json={"level": "autopilot"})
    client.put("/settings/ai-disclosure", json={"enabled": False})
    llm.reply = drafted(OPENER)


def sync(app, client, tinder, *names: str) -> list[dict]:
    """The user connects Tinder, the matches named sync, and the worker runs. Returns their cards."""
    tinder.names = list(names)
    assert client.put("/connectors/tinder/token", json={"token": TOKEN}).status_code == 204
    work_now(app)
    return [card for card in client.get("/cards").json() if card["name"] in names]


def test_an_opener_goes_out_30_minutes_to_6_hours_after_the_match_synced(app, client, llm, tinder, autopilot):
    """Claude asks for the soonest time it may, on an evening when the formula alone would wait 22 minutes."""
    at_local_hour(client, 20)
    client.patch("/settings", json={"night_window_start": 0, "night_window_end": 0})  # no night window
    llm.reply = drafted(OPENER, adjustment=-0.5)

    (card,) = sync(app, client, tinder, "Ana")

    wait = send_at(card["planned_send"]) - datetime.fromisoformat(card["created_at"])
    assert timedelta(minutes=30) <= wait <= timedelta(hours=6)
    assert card["planned_send"]["kind"] == "opener"


def test_an_opener_never_lands_inside_the_night_window(app, client, tinder, autopilot):
    """The user's night window covers the whole half hour to 6 hours after the match."""
    zone = at_local_hour(client, 12)
    client.patch("/settings", json={"night_window_start": 12, "night_window_end": 19})

    (card,) = sync(app, client, tinder, "Ana")

    assert not 12 <= send_at(card["planned_send"]).astimezone(zone).hour < 19


def test_openers_for_matches_synced_together_are_at_least_ten_minutes_apart(app, client, tinder, autopilot):
    """Twenty openers in five and a half hours: at random times, two would almost surely land closer."""
    at_local_hour(client, 12)  # the night window is hours away

    cards = sync(app, client, tinder, *(f"Match {number}" for number in range(20)))

    times = sorted(send_at(card["planned_send"]) for card in cards)
    assert len(times) == 20
    assert min(later - earlier for earlier, later in pairwise(times)) >= timedelta(minutes=10)


def test_a_new_match_is_handled_by_autopilot_while_it_writes_the_opener_and_until_the_opener_goes_out(
    app, client, tinder, autopilot
):
    tinder.names = ["Ana"]
    client.put("/connectors/tinder/token", json={"token": TOKEN})
    run_once(app.state.engine)  # the sync, not yet the opener job it queues

    card = placed(client, "Ana")
    assert (card["pipeline_group"], card["autopilot_activity"]) == ("handled_by_autopilot", "writing_opener")

    work_now(app)

    card = placed(client, "Ana")
    assert (card["pipeline_group"], card["autopilot_activity"]) == ("handled_by_autopilot", "planned")
    assert (card["planned_send"]["original"], card["planned_send"]["kind"]) == (OPENER, "opener")


def test_the_opener_goes_out_at_its_send_time(app, client, tinder, autopilot):
    sync(app, client, tinder, "Ana")

    work_after_send_time(app)

    assert tinder.sent == [OPENER]


def test_an_opener_is_dropped_when_the_user_writes_first(app, client, tinder, autopilot):
    """They wrote on Tinder themselves and sync brought the message in: the opener would cross it."""
    (card,) = sync(app, client, tinder, "Ana")
    client.post(f"/cards/{card['id']}/messages", json={"sender": "me", "body": "ana! finally"})

    work_after_send_time(app)

    assert tinder.sent == []
    assert client.get("/queue").json() == []  # dropped, not left for the user
