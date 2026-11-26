"""Send timing (ADR 0008): autopilot plans when each reply goes out, inside hard bounds no model output crosses.

Claude's fake writes the reply with a chosen adjustment. The match's messages go in through the API, the reply
job runs, and the planned send is read from the card summary. The user's time zone is chosen so that it is a
known hour of their day now, whatever the clock says.
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.test_drafts import drafted, write_profile
from tests.test_send import CLEO, tinder, user_id, work_after_send_time, work_now  # noqa: F401  (fixtures)

REPLY = "both. badly."


@pytest.fixture
def card_id(app, client, llm, user_id, tinder) -> int:  # noqa: F811
    """Cleo's Tinder card, with chat autopilot on and the AI disclosure off. Tinder is the stub."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.put("/autonomy/chat", json={"level": "autopilot"})
    client.put("/settings/ai-disclosure", json={"enabled": False})
    llm.reply = drafted(REPLY)
    return client.post("/cards", json={"app": "tinder", "name": "Cleo", "external_id": CLEO}).json()["id"]


def at_local_hour(client, hour: int) -> ZoneInfo:
    """Give the user the time zone in which it is now `hour` o'clock, and return it."""
    offset = (hour - datetime.now(UTC).hour + 12) % 24 - 12  # hours ahead of UTC, -12 to 11
    name = f"Etc/GMT{-offset:+d}" if offset else "UTC"  # Etc/GMT-3 is three hours ahead of UTC
    assert client.patch("/settings", json={"time_zone": name}).status_code == 200
    return ZoneInfo(name)


def chat(client, card_id: int, *messages: tuple[str, float, str]) -> None:
    """Store the messages, each `(sender, minutes ago, body)`, oldest first."""
    now = datetime.now(UTC)
    for sender, ago, body in messages:
        sent_at = (now - timedelta(minutes=ago)).isoformat()
        response = client.post(f"/cards/{card_id}/messages", json={"sender": sender, "body": body, "sent_at": sent_at})
        assert response.status_code == 201


def planned_send(client, card_id: int) -> dict:
    return client.get(f"/cards/{card_id}").json()["planned_send"]


def send_at(planned: dict) -> datetime:
    return datetime.fromisoformat(planned["send_at"])


def plan(app, client, card_id: int) -> timedelta:
    """Run the reply job and return how long after its run the planned send goes out (it runs well under 5 s)."""
    started = datetime.now(UTC)
    work_now(app)
    return send_at(planned_send(client, card_id)) - started


def test_a_live_match_gets_a_reply_no_sooner_than_two_minutes(app, client, llm, card_id):
    """They answer within a minute, so the formula waits under two minutes, and Claude asks for less still."""
    at_local_hour(client, 11)
    llm.reply = drafted(REPLY, adjustment=-0.5)
    chat(client, card_id, ("me", 3, "climbing?"), ("them", 2, "yes!! you?"), ("me", 1, "badly"), ("them", 0, "same"))

    wait = plan(app, client, card_id)

    assert timedelta(minutes=2) <= wait < timedelta(minutes=2, seconds=5)


def test_a_match_who_is_not_live_gets_a_reply_no_sooner_than_ten_minutes(app, client, llm, card_id):
    """They answer within a minute but wrote six minutes ago: the formula's time has passed."""
    at_local_hour(client, 11)
    llm.reply = drafted(REPLY, adjustment=-0.5)
    chat(client, card_id, ("me", 9, "climbing?"), ("them", 8, "yes!! you?"), ("me", 7, "badly"), ("them", 6, "same"))

    wait = plan(app, client, card_id)

    assert timedelta(minutes=10) <= wait < timedelta(minutes=10, seconds=5)


def test_no_reply_is_planned_more_than_twelve_hours_out(app, client, llm, card_id):
    """They took 20 hours to answer with a word, and Claude asks for much longer still."""
    at_local_hour(client, 11)  # 12 hours on is 23:00, outside the night window
    llm.reply = drafted(REPLY, adjustment=3)
    chat(client, card_id, ("me", 20 * 60, "how was the trip"), ("them", 1, "ok"))

    wait = plan(app, client, card_id)

    assert timedelta(hours=12) <= wait < timedelta(hours=12, seconds=5)


def test_a_send_time_inside_the_night_window_moves_to_its_end(app, client, card_id):
    zone = at_local_hour(client, 3)
    chat(client, card_id, ("them", 0, "do you climb indoors or outdoors"))
    today = datetime.now(zone).date()

    plan(app, client, card_id)

    local = send_at(planned_send(client, card_id)).astimezone(zone)
    assert local.date() == today
    assert time(7, 0) < local.time() <= time(7, 15)  # a few random minutes after 07:00


def test_a_send_time_inside_a_night_window_the_user_set_moves_to_its_end(app, client, card_id):
    zone = at_local_hour(client, 22)
    client.patch("/settings", json={"night_window_start": 22, "night_window_end": 9})
    chat(client, card_id, ("them", 0, "do you climb indoors or outdoors"))
    tomorrow = datetime.now(zone).date() + timedelta(days=1)

    plan(app, client, card_id)

    local = send_at(planned_send(client, card_id)).astimezone(zone)
    assert local.date() == tomorrow
    assert time(9, 0) < local.time() <= time(9, 15)


def test_the_night_window_is_one_to_seven_by_default_and_takes_only_hours_of_the_day(client):
    settings = client.get("/settings").json()
    assert (settings["night_window_start"], settings["night_window_end"]) == (1, 7)

    assert client.patch("/settings", json={"night_window_end": 24}).status_code == 422
    assert client.patch("/settings", json={"night_window_start": -1}).status_code == 422


@pytest.mark.parametrize("asked, half", [(-3, -0.5), (3, 0.5)])
def test_claudes_adjustment_is_clamped_to_half_of_the_formulas_time_either_way(
    app, client, llm, card_id, asked, half
):
    """Two matches write the same message at the same time: Claude asking for more than half moves the send time
    no further than half does."""
    at_local_hour(client, 11)
    other = client.post("/cards", json={"app": "tinder", "name": "Ada", "external_id": "match-ada"}).json()["id"]
    waits = []
    for card, adjustment in ((card_id, half), (other, asked)):
        llm.reply = drafted(REPLY, adjustment=adjustment)
        chat(client, card, ("them", 0, "do you climb indoors or outdoors"))
        waits.append(plan(app, client, card))

    assert abs(waits[0] - waits[1]) < timedelta(seconds=5)


def test_a_planned_send_does_not_go_out_when_autopilot_is_paused_at_its_send_time(app, client, card_id, tinder):  # noqa: F811
    chat(client, card_id, ("them", 0, "do you climb indoors or outdoors"))
    work_now(app)
    client.post("/autopilot/pause")

    work_after_send_time(app)

    assert tinder.sent == []
    assert [item["draft"]["original"] for item in client.get("/queue").json()] == [REPLY]  # held for the user


def test_a_new_message_before_the_send_time_cancels_the_planned_send_and_plans_a_new_reply(
    app, client, llm, card_id, tinder  # noqa: F811
):
    llm.reply = drafted(REPLY)
    chat(client, card_id, ("them", 0, "do you climb indoors or outdoors"))
    work_now(app)
    first = planned_send(client, card_id)
    llm.reply = drafted("outdoors, obviously")

    chat(client, card_id, ("them", 0, "wait, which one?"))
    work_now(app)

    second = planned_send(client, card_id)
    assert (second["id"] != first["id"], second["original"]) == (True, "outdoors, obviously")
    work_after_send_time(app)
    assert [body["message"] for _, body in tinder.sent] == ["outdoors, obviously"]
    assert client.get("/queue").json() == []  # the dropped reply is not left for the user


def test_a_planned_send_shows_on_the_card_with_its_time_and_reason_and_autopilot_handles_the_card(
    app, client, llm, card_id
):
    llm.reply = drafted(REPLY, timing_reason="they take their time")
    chat(client, card_id, ("them", 0, "do you climb indoors or outdoors"))

    work_now(app)

    card = client.get(f"/cards/{card_id}").json()
    planned = card["planned_send"]
    assert (planned["original"], planned["status"], planned["timing_reason"]) == (REPLY, "approved", "they take their time")
    assert send_at(planned) > datetime.now(UTC)
    assert (card["pipeline_group"], card["reason"], card["autopilot_activity"]) == ("handled_by_autopilot", None, "planned")
    assert card["drafts"] == []  # the card's draft list holds what waits for the user


def test_a_copilot_draft_carries_a_suggested_send_time_inside_the_bounds_with_a_reason(app, client, llm, user_id):  # noqa: F811
    """The user asks for a draft on a slow chat, and Claude wants it much later still: the ceiling holds."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "tinder", "name": "Cleo", "external_id": CLEO}).json()["id"]
    at_local_hour(client, 11)  # 12 hours on is 23:00, outside the night window
    chat(client, card_id, ("me", 20 * 60, "how was the trip"), ("them", 1, "ok"))
    llm.reply = drafted(REPLY, adjustment=3, timing_reason="they take their time")
    started = datetime.now(UTC)

    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert timedelta(hours=12) <= send_at(draft) - started < timedelta(hours=12, seconds=5)
    assert draft["timing_reason"] == "they take their time"
