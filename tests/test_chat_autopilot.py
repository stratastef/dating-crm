"""Chat autopilot: with chat autonomy at Autopilot or Full autopilot, the worker replies to matches on its own.

Tinder, Claude, Jev and Google are the stubs. A message from the match goes in through the API, the worker
runs, and what was sent is read from the Tinder stub.
"""

from datetime import UTC, datetime, timedelta

import pytest
from test_send import CLEO, tinder, user_id, work  # noqa: F401  (fixtures)

from app.jev import GUARDRAIL, JevUnavailable
from app.jobs import run_once
from app.send import queue_send
from app.vault import store_token

REPLY = "both. badly."
DISCLOSURE = "an AI assistant helps me write"


@pytest.fixture
def card_id(app, client, llm, user_id) -> int:  # noqa: F811
    """Cleo's Tinder card, for a user whose style profile is written."""
    llm.reply = "Short, lowercase, teasing."
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    work(app)
    llm.reply = REPLY
    return client.post("/cards", json={"app": "tinder", "name": "Cleo", "external_id": CLEO}).json()["id"]


def autonomy(client, level: str) -> None:
    assert client.put("/autonomy/chat", json={"level": level}).status_code == 200


def incoming(client, card_id: int, body: str = "do you climb indoors or outdoors") -> None:
    assert client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": body}).status_code == 201


def sent(tinder) -> list[str]:  # noqa: F811
    return [body["message"] for _, body in tinder.sent]


def queued_for_review(client) -> list[dict]:
    return [item["draft"] for item in client.get("/queue").json() if item["kind"] == "draft"]


@pytest.mark.parametrize("level", ["autopilot", "full_autopilot"])
def test_autopilot_replies_to_a_match_on_its_own_and_logs_the_send_with_its_trigger(
    app, client, card_id, tinder, level  # noqa: F811
):
    client.put("/settings/ai-disclosure", json={"enabled": False})
    autonomy(client, level)

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == [REPLY]
    assert queued_for_review(client) == []
    (action,) = client.get("/audit-log").json()
    assert (action["type"], action["app"], action["target"]) == ("message", "tinder", f"card:{card_id}")
    assert action["trigger"].startswith(f"chat autopilot ({level})")


# (a) Nothing is sent unattended unless chat autonomy is Autopilot or Full autopilot and nothing is paused.


def run_reply_job(app) -> None:
    """Run the one `chat_reply` job that is due, and not the send it queues."""
    assert run_once(app.state.engine)


def test_in_copilot_nothing_is_sent_and_nothing_is_drafted(app, client, card_id, tinder):  # noqa: F811
    incoming(client, card_id)  # chat autonomy is copilot by default
    work(app)

    assert sent(tinder) == []
    assert queued_for_review(client) == []


@pytest.mark.parametrize("scope", [{}, {"app": "tinder"}])
def test_a_pause_stops_autopilot_replies(app, client, card_id, tinder, scope):  # noqa: F811
    autonomy(client, "full_autopilot")
    client.post("/autopilot/pause", params=scope)

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []


def test_a_pause_after_the_message_arrived_stops_the_reply(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")
    incoming(client, card_id)
    client.post("/autopilot/pause")

    work(app)

    assert sent(tinder) == []
    assert queued_for_review(client) == []  # the worker skipped the job before Claude was called


def test_autonomy_lowered_before_the_send_keeps_the_reply_for_the_user(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")
    incoming(client, card_id)
    run_reply_job(app)
    autonomy(client, "copilot")

    work(app)

    assert sent(tinder) == []
    assert [draft["status"] for draft in queued_for_review(client)] == ["pending"]


def test_a_ban_signal_from_the_app_stops_further_replies(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")
    tinder.status = 403
    incoming(client, card_id)
    work(app)  # the send is refused: ban detection pauses Tinder
    assert client.get("/autopilot/pause").json()["apps"] == ["tinder"]
    tinder.status = 200
    tinder.sent.clear()

    incoming(client, card_id, "hello?")
    work(app)

    assert sent(tinder) == []


def test_autopilot_stops_at_the_ai_budget_cap(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "full_autopilot")
    client.put("/budget", json={"cap_usd": 0})

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []


# (b) Every outgoing message passes the draft guardrail first; a hit goes to the review queue.


def test_a_guardrail_hit_routes_the_reply_to_the_review_queue_instead_of_sending(
    app, client, card_id, tinder, jev  # noqa: F811
):
    autonomy(client, "autopilot")
    jev.yes["overpromise"] = ["badly"]

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []
    (draft,) = queued_for_review(client)
    assert (draft["status"], draft["guardrail"]) == ("pending", ["overpromise"])
    assert client.get("/audit-log").json() == []


def test_without_jev_the_reply_goes_to_the_review_queue(app, client, card_id, tinder, monkeypatch):  # noqa: F811
    def guardrail_down(sentence: str, check: str) -> bool:
        if check in GUARDRAIL:
            raise JevUnavailable("down")
        return False

    monkeypatch.setattr("app.jev.ask", guardrail_down)
    autonomy(client, "full_autopilot")

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []
    assert [draft["guardrail"] for draft in queued_for_review(client)] == [["unavailable"]]


def test_queue_send_refuses_an_unattended_send_of_a_draft_with_a_guardrail_hit(
    app, client, card_id, user_id, tinder, jev  # noqa: F811
):
    autonomy(client, "autopilot")
    jev.yes["protected_trait"] = ["badly"]
    draft = client.post(f"/cards/{card_id}/drafts").json()

    with app.state.engine.begin() as db:
        assert queue_send(db, user_id, draft["id"], "test", unattended=True) is None
    work(app)

    assert sent(tinder) == []
    assert [queued["status"] for queued in queued_for_review(client)] == ["pending"]


def test_the_users_own_tap_sends_a_draft_they_have_read_despite_a_hit(app, client, card_id, tinder, jev):  # noqa: F811
    jev.yes["overpromise"] = ["badly"]
    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert client.post(f"/drafts/{draft['id']}/send").status_code == 202
    work(app)

    assert sent(tinder) == [REPLY]


# (g) The "denies being AI" rule is never bypassed, by autopilot or by a tap.


def test_a_draft_that_denies_being_ai_is_never_sent_until_it_is_edited(app, client, card_id, tinder, jev):  # noqa: F811
    autonomy(client, "full_autopilot")
    jev.yes["denies_ai"] = ["badly"]
    incoming(client, card_id)
    work(app)
    (draft,) = queued_for_review(client)
    assert sent(tinder) == []

    refused = client.post(f"/drafts/{draft['id']}/send")
    assert refused.status_code == 409
    assert "denies being AI" in refused.json()["detail"]
    work(app)
    assert sent(tinder) == []

    client.patch(f"/drafts/{draft['id']}", json={"edited": "both, poorly"})
    assert client.post(f"/drafts/{draft['id']}/send").status_code == 202
    work(app)
    assert sent(tinder) == ["both, poorly"]


# (c) A card paused for handover or taken over is never sent to.


@pytest.mark.parametrize("level", ["autopilot", "full_autopilot"])
def test_a_handover_trigger_stops_the_reply_in_both_modes(app, client, card_id, tinder, jev, level):  # noqa: F811
    autonomy(client, level)
    jev.yes["personal_info"] = ["number"]

    incoming(client, card_id, "what's your number?")
    work(app)

    assert sent(tinder) == []
    assert client.get(f"/cards/{card_id}").json()["handover"] == "pending"


def test_a_card_the_user_took_over_gets_no_reply(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "full_autopilot")
    client.post(f"/cards/{card_id}/take-over")

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []


def test_a_take_over_before_the_send_keeps_the_reply_for_the_user(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")
    incoming(client, card_id)
    run_reply_job(app)
    client.post(f"/cards/{card_id}/take-over")

    work(app)

    assert sent(tinder) == []
    assert [draft["status"] for draft in queued_for_review(client)] == ["pending"]


# (d) The app stops chatting once numbers are swapped.


@pytest.mark.parametrize("stage", ["number_swapped", "date_set", "dated", "seeing_them", "archived"])
def test_no_reply_is_sent_from_number_swapped_on(app, client, card_id, tinder, stage):  # noqa: F811
    autonomy(client, "full_autopilot")
    client.patch(f"/cards/{card_id}", json={"stage": stage})

    incoming(client, card_id)
    work(app)

    assert sent(tinder) == []


def test_numbers_swapped_before_the_send_keeps_the_reply_for_the_user(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "full_autopilot")
    incoming(client, card_id)
    run_reply_job(app)
    client.patch(f"/cards/{card_id}", json={"stage": "number_swapped"})

    work(app)

    assert sent(tinder) == []
    assert [draft["status"] for draft in queued_for_review(client)] == ["pending"]


# (e) Date logistics: Autopilot hands them to the user; Full autopilot offers only free slots and holds each.


@pytest.fixture
def evenings(app, user_id, gcal) -> list[datetime]:  # noqa: F811
    """The calendar is connected. The start of each of the next evenings Full autopilot may offer, in UTC."""
    with app.state.engine.begin() as db:
        store_token(db, user_id, "google_calendar", "refresh-token")
    first = (datetime.now(UTC) + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
    return [first + timedelta(days=day) for day in range(7)]


def said(start: datetime) -> str:
    return start.strftime("%a %d %b %H:%M")


def test_guardrails_mode_hands_date_logistics_to_the_user(app, client, card_id, tinder, jev, gcal, evenings):  # noqa: F811
    autonomy(client, "autopilot")
    jev.yes["logistics"] = ["when are you free"]

    incoming(client, card_id, "when are you free?")
    work(app)

    assert sent(tinder) == []
    assert gcal.events == {}
    assert client.get(f"/cards/{card_id}").json()["handover"] == "pending"


def test_full_mode_offers_only_free_slots_and_holds_each_one(app, client, card_id, tinder, jev, gcal, evenings):  # noqa: F811
    client.put("/settings/ai-disclosure", json={"enabled": False})
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free"]
    gcal.busy = [(evenings[0], evenings[0] + timedelta(hours=1))]  # tomorrow evening is taken

    incoming(client, card_id, "when are you free?")
    work(app)

    assert sent(tinder) == [f"{REPLY} I'm free {said(evenings[1])} or {said(evenings[2])}."]
    held = sorted((event["start"], event["end"], event["status"]) for event in gcal.events.values())
    assert held == [
        (evenings[1], evenings[1] + timedelta(hours=2), "tentative"),
        (evenings[2], evenings[2] + timedelta(hours=2), "tentative"),
    ]
    holds = [entry for entry in client.get("/audit-log").json() if entry["type"] == "calendar_hold"]
    assert len(holds) == 2
    assert all(entry["trigger"] == "chat autopilot (full): offered a time" for entry in holds)


def test_full_mode_never_sends_a_time_claude_made_up(app, client, card_id, tinder, jev, gcal, evenings, llm):  # noqa: F811
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "friday at 9"]
    llm.reply = "friday at 9?"

    incoming(client, card_id, "when are you free?")
    work(app)

    assert sent(tinder) == []
    assert gcal.events == {}
    assert [draft["guardrail"] for draft in queued_for_review(client)] == [["logistics"]]


def test_full_mode_without_a_connected_calendar_hands_logistics_to_the_user(app, client, card_id, tinder, jev):  # noqa: F811
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free"]

    incoming(client, card_id, "when are you free?")
    work(app)

    assert sent(tinder) == []
    assert [draft["guardrail"] for draft in queued_for_review(client)] == [["logistics"]]


def test_full_mode_books_the_date_the_match_agrees_to_and_then_stops(
    app, client, card_id, tinder, jev, gcal, evenings, llm  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "works for me"]
    incoming(client, card_id, "when are you free?")
    work(app)
    assert len(sent(tinder)) == 1
    llm.replies = ["2", "can't wait"]  # Claude reads the answer as the second time offered, then drafts

    incoming(client, card_id, "the second one works for me")
    work(app)

    assert [(event["start"], event["status"]) for event in gcal.events.values()] == [(evenings[1], "confirmed")]
    assert client.get(f"/cards/{card_id}").json()["stage"] == "date_set"
    assert len(sent(tinder)) == 1  # the booked date is where autopilot ends
    assert [draft["original"] for draft in queued_for_review(client)] == ["can't wait"]

    incoming(client, card_id, "see you there")
    work(app)
    assert len(sent(tinder)) == 1


def test_booking_a_date_tells_the_calendar_that_the_cards_stage_changed(
    app, client, card_id, tinder, jev, gcal, evenings, llm, monkeypatch  # noqa: F811
):
    """Code that sets a stage without the PATCH route must call `calendar.stage_changed()`."""
    changes = []
    monkeypatch.setattr("app.calendar.stage_changed", lambda db, user_id, card, stage: changes.append((card, stage)))
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "works for me"]
    incoming(client, card_id, "when are you free?")
    work(app)
    llm.replies = ["2", "can't wait"]

    incoming(client, card_id, "the second one works for me")
    work(app)

    assert client.get(f"/cards/{card_id}").json()["stage"] == "date_set"
    assert changes == [(card_id, "date_set")]


def test_full_mode_releases_the_holds_a_match_declines_and_offers_other_times(
    app, client, card_id, tinder, jev, gcal, evenings, llm  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "neither works"]
    incoming(client, card_id, "when are you free?")
    work(app)
    llm.replies = ["none", "no worries"]

    incoming(client, card_id, "neither works, sorry")
    work(app)

    # The declined evenings are free again, so they are what the calendar offers; each is held once.
    assert sorted(event["start"] for event in gcal.events.values()) == evenings[:2]
    releases = [entry for entry in client.get("/audit-log").json() if " release " in entry["target"]]
    assert len(releases) == 2
    assert len(sent(tinder)) == 2


def test_full_mode_hands_over_an_answer_that_neither_accepts_nor_declines(
    app, client, card_id, tinder, jev, gcal, evenings, llm  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "where"]
    incoming(client, card_id, "when are you free?")
    work(app)
    llm.replies = ["other", "good question"]

    incoming(client, card_id, "where would we go?")
    work(app)

    assert len(sent(tinder)) == 1
    assert len(gcal.events) == 2  # the offered times stay held
    assert [draft["guardrail"] for draft in queued_for_review(client)] == [["logistics"]]


# Every slot a draft offers is held, in every mode, and the hold goes when the draft is dismissed or fails.


def test_a_copilot_draft_that_answers_a_question_about_time_offers_free_slots_and_holds_each(
    app, client, card_id, jev, gcal, evenings  # noqa: F811
):
    jev.yes["logistics"] = ["when are you free"]
    incoming(client, card_id, "when are you free?")  # chat autonomy is copilot

    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert draft["original"] == f"{REPLY} I'm free {said(evenings[0])} or {said(evenings[1])}."
    assert sorted(event["start"] for event in gcal.events.values()) == evenings[:2]
    assert {event["status"] for event in gcal.events.values()} == {"tentative"}

    assert client.post(f"/drafts/{draft['id']}/dismiss").status_code == 200
    assert gcal.events == {}


def test_dismissing_a_reply_autopilot_kept_for_the_user_releases_the_slots_it_offered(
    app, client, card_id, tinder, jev, gcal, evenings  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes = {"logistics": ["when are you free"], "overpromise": ["badly"]}
    incoming(client, card_id, "when are you free?")
    work(app)
    (draft,) = queued_for_review(client)
    assert len(gcal.events) == 2

    client.post(f"/drafts/{draft['id']}/dismiss")

    assert gcal.events == {}


def test_a_send_that_fails_releases_the_slots_the_message_offered(app, client, card_id, tinder, jev, gcal, evenings):  # noqa: F811
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free"]
    tinder.status = 500

    incoming(client, card_id, "when are you free?")
    work(app)

    assert gcal.events == {}


def test_dismissing_a_later_draft_keeps_the_slots_an_earlier_message_offered(
    app, client, card_id, tinder, jev, gcal, evenings, llm  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free", "where"]
    incoming(client, card_id, "when are you free?")
    work(app)
    llm.replies = ["other", "good question"]
    incoming(client, card_id, "where would we go?")
    work(app)
    (draft,) = queued_for_review(client)

    client.post(f"/drafts/{draft['id']}/dismiss")

    assert len(gcal.events) == 2


@pytest.mark.parametrize("message", ["let's meet at joe's bar", "are we exclusive?"])
def test_full_mode_hands_a_place_or_exclusivity_to_the_user(
    app, client, card_id, tinder, jev, gcal, evenings, message  # noqa: F811
):
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = jev.yes["place_or_exclusivity"] = ["joe's bar", "exclusive"]

    incoming(client, card_id, message)
    work(app)

    assert sent(tinder) == []
    assert gcal.events == {}
    assert client.get(f"/cards/{card_id}").json()["handover"] == "pending"


def test_full_mode_offers_times_when_the_question_is_not_the_newest_message(
    app, client, card_id, tinder, jev, gcal, evenings  # noqa: F811
):
    client.put("/settings/ai-disclosure", json={"enabled": False})
    autonomy(client, "full_autopilot")
    jev.yes["logistics"] = ["when are you free"]

    incoming(client, card_id, "when are you free?")
    incoming(client, card_id, "??")
    work(app)

    assert sent(tinder) == [f"{REPLY} I'm free {said(evenings[0])} or {said(evenings[1])}."]


# (g) AI disclosure.


def test_the_first_unattended_message_to_a_match_discloses_the_ai_by_default(app, client, card_id, tinder):  # noqa: F811
    assert client.get("/settings/ai-disclosure").json() == {"enabled": True}
    autonomy(client, "autopilot")

    incoming(client, card_id)
    work(app)
    incoming(client, card_id, "and bouldering?")
    work(app)

    first, second = sent(tinder)
    assert first.startswith(REPLY) and DISCLOSURE in first
    assert second == REPLY


def test_the_card_says_whether_the_ai_was_disclosed_to_the_match(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")
    assert client.get(f"/cards/{card_id}").json()["ai_disclosed"] is False

    incoming(client, card_id)
    work(app)

    assert client.get(f"/cards/{card_id}").json()["ai_disclosed"] is True


def test_a_match_who_got_undisclosed_replies_is_told_once_the_disclosure_is_turned_on(
    app, client, card_id, tinder  # noqa: F811
):
    client.put("/settings/ai-disclosure", json={"enabled": False})
    autonomy(client, "autopilot")
    incoming(client, card_id)
    work(app)
    assert client.get(f"/cards/{card_id}").json()["ai_disclosed"] is False

    client.put("/settings/ai-disclosure", json={"enabled": True})
    incoming(client, card_id, "and bouldering?")
    work(app)

    assert DISCLOSURE not in sent(tinder)[0] and DISCLOSURE in sent(tinder)[1]


def test_the_disclosure_is_checked_by_the_guardrail_like_the_rest_of_the_message(
    app, client, card_id, tinder, jev  # noqa: F811
):
    autonomy(client, "autopilot")

    incoming(client, card_id)
    work(app)

    assert any(DISCLOSURE in sentence and check == "denies_ai" for sentence, check in jev.asked)


# Replies are not doubled, and old chats are left alone.


def test_two_messages_in_a_row_get_one_reply(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "autopilot")

    incoming(client, card_id)
    incoming(client, card_id, "hello?")
    work(app)

    assert len(sent(tinder)) == 1


def test_a_reply_waits_for_the_user_when_an_older_unanswered_message_was_never_checked(
    app, client, card_id, tinder, jev  # noqa: F811
):
    """Old messages are not sent to Jev, so autopilot cannot know that one of them was a handover trigger."""
    autonomy(client, "full_autopilot")
    jev.yes["asks_if_ai"] = ["are you a bot"]
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "are you a bot?", "sent_at": old})

    incoming(client, card_id, "hello?")
    work(app)

    assert sent(tinder) == []
    assert [draft["guardrail"] for draft in queued_for_review(client)] == [["unchecked"]]


def test_an_old_message_is_not_answered(app, client, card_id, tinder):  # noqa: F811
    autonomy(client, "full_autopilot")
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()

    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "hey", "sent_at": old})
    work(app)

    assert sent(tinder) == []
    assert queued_for_review(client) == []
