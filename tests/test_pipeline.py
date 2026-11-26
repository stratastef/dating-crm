"""The Pipeline: every card grouped by who acts next (ADR 0007, spec #44 "Pipeline grouping").

Cards, messages, drafts and settings go in through the API; `GET /pipeline` is read back.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.test_drafts import write_profile
from tests.test_send import draft, tinder, user_id, work  # noqa: F401  (fixtures)
from tests.test_stalled import run_scheduled_jobs


def ago(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat()


def new_card(client, name: str, stage: str = "chatting", app: str = "hinge", **fields) -> int:
    response = client.post("/cards", json={"app": app, "name": name, "stage": stage, **fields})
    assert response.status_code == 201
    return response.json()["id"]


def message(client, card_id: int, sender: str, sent_at: str | None = None, body: str = "hey") -> None:
    sent = {"sender": sender, "body": body} | ({"sent_at": sent_at} if sent_at else {})
    assert client.post(f"/cards/{card_id}/messages", json=sent).status_code == 201


def pipeline(client) -> dict[str, list[str]]:
    """`GET /pipeline` as {group: card names, in order}."""
    response = client.get("/pipeline")
    assert response.status_code == 200
    return {group["group"]: [card["name"] for card in group["cards"]] for group in response.json()}


def placed(client, name: str) -> dict:
    """The card's summary as the Pipeline lists it."""
    return next(card for group in client.get("/pipeline").json() for card in group["cards"] if card["name"] == name)


def test_the_pipeline_lists_its_groups_in_order_and_leaves_empty_groups_out(client):
    new_card(client, "Ada", stage="archived")
    message(client, new_card(client, "Kim"), "them")

    assert list(pipeline(client)) == ["waiting_for_you", "archived"]
    assert placed(client, "Kim")["pipeline_group"] == "waiting_for_you"
    assert placed(client, "Ada")["pipeline_group"] == "archived"


# Waiting for you: each reason, in precedence order.


def test_a_pending_handover_waits_for_you_with_the_check_that_hit(client, jev):
    jev.yes["logistics"] = ["saturday"]
    message(client, new_card(client, "Ada"), "them", body="Saturday at 8?")

    card = placed(client, "Ada")

    assert (card["pipeline_group"], card["reason"], card["handover_trigger"]) == ("waiting_for_you", "handover", "logistics")


def test_a_pending_draft_waits_for_you_whatever_the_stage(app, client, llm):
    """Precedence: a Number swapped card is Texting off-app, unless a draft of it waits in Review."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = new_card(client, "Ada", stage="number_swapped")
    assert placed(client, "Ada")["pipeline_group"] == "texting_off_app"

    client.post(f"/cards/{card_id}/drafts")

    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "draft_in_review")


def test_a_failed_send_waits_for_you(app, client, draft, tinder):  # noqa: F811
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)

    card = placed(client, "Cleo")

    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "failed_send")


def test_a_copied_draft_waits_for_you_after_a_draft_in_review_and_before_a_failed_send(
    app, client, draft, tinder  # noqa: F811
):
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)
    copied = client.post(f"/cards/{draft['card_id']}/drafts").json()
    client.post(f"/drafts/{copied['id']}/copy")

    card = placed(client, "Cleo")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "copied_draft")

    client.post(f"/cards/{draft['card_id']}/drafts")

    assert placed(client, "Cleo")["reason"] == "draft_in_review"


def test_a_stalled_card_waits_for_you(app, client):
    message(client, new_card(client, "Ada", stage="date_set"), "me", sent_at=ago(days=4))
    assert placed(client, "Ada")["pipeline_group"] == "texting_off_app"

    run_scheduled_jobs(app)

    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "stalled")


def test_a_next_action_due_today_is_not_overdue_until_the_day_after(client):
    today = datetime.now(UTC).date()
    card_id = new_card(client, "Ada", stage="number_swapped", next_action="Book the bar", due_date=today.isoformat())
    assert placed(client, "Ada")["pipeline_group"] == "texting_off_app"

    client.patch(f"/cards/{card_id}", json={"due_date": (today - timedelta(days=1)).isoformat()})

    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "overdue")


def test_overdue_follows_the_users_time_zone(client):
    """Kiritimati is 25 hours ahead of Pago Pago: its yesterday is still today or tomorrow in Pago Pago."""
    kiritimati_yesterday = datetime.now(ZoneInfo("Pacific/Kiritimati")).date() - timedelta(days=1)
    new_card(client, "Ada", stage="number_swapped", next_action="Book the bar", due_date=kiritimati_yesterday.isoformat())

    client.patch("/settings", json={"time_zone": "Pacific/Pago_Pago"})
    assert placed(client, "Ada")["reason"] is None

    client.patch("/settings", json={"time_zone": "Pacific/Kiritimati"})
    assert placed(client, "Ada")["reason"] == "overdue"


def test_a_dated_card_waits_for_you_until_the_date_is_rated(client):
    card_id = new_card(client, "Ada", stage="dated")
    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "rate_date")

    client.patch(f"/cards/{card_id}", json={"date_rating": 5})

    assert placed(client, "Ada")["pipeline_group"] == "texting_off_app"


def test_a_chat_autopilot_cannot_answer_is_your_turn_when_the_match_wrote_last(client):
    card_id = new_card(client, "Ada")
    message(client, card_id, "me", sent_at=ago(hours=2))
    assert placed(client, "Ada")["pipeline_group"] == "waiting_for_them"

    message(client, card_id, "them", sent_at=ago(hours=1))

    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "your_turn")


def test_a_matched_card_autopilot_cannot_write_to_waits_for_your_opener(client):
    new_card(client, "Ada", stage="matched")

    card = placed(client, "Ada")

    assert (card["pipeline_group"], card["reason"]) == ("waiting_for_you", "opener_due")


# Handled by autopilot, and Waiting for them when autopilot cannot act.


def autonomy(client, level: str) -> None:
    assert client.put("/autonomy/chat", json={"level": level}).status_code == 200


def linked(client, name: str, external_id: str, stage: str = "chatting") -> int:
    """A Tinder card linked to its match. The `user_id` fixture stores the user's Tinder session token."""
    return new_card(client, name, stage=stage, app="tinder", external_id=external_id)


def test_autopilot_handles_the_chats_it_can_act_on_and_says_what_it_is_doing(client, user_id):  # noqa: F811
    autonomy(client, "autopilot")
    message(client, linked(client, "Kim", "match-kim"), "them")  # queues autopilot's reply
    message(client, linked(client, "Sam", "match-sam"), "me", sent_at=ago(days=1))

    activities = {name: placed(client, name)["autopilot_activity"] for name in ("Kim", "Sam")}

    assert pipeline(client) == {"handled_by_autopilot": ["Kim", "Sam"]}
    assert activities == {"Kim": "drafting_reply", "Sam": "sent_waiting"}


def test_a_match_added_by_hand_waits_for_your_opener(client, user_id):  # noqa: F811
    """Chat autopilot writes openers only to new matches sync finds (`tests/test_openers.py`)."""
    autonomy(client, "autopilot")
    linked(client, "Ada", "match-ada", stage="matched")

    card = placed(client, "Ada")

    assert (card["pipeline_group"], card["reason"], card["autopilot_activity"]) == ("waiting_for_you", "opener_due", None)


def test_a_match_reply_autopilot_did_not_answer_is_your_turn(app, client, user_id):  # noqa: F811
    """No style profile yet, so the reply job writes nothing: the match waits for the user, not for autopilot."""
    autonomy(client, "autopilot")
    message(client, linked(client, "Kim", "match-kim"), "them")

    work(app)

    card = placed(client, "Kim")
    assert (card["pipeline_group"], card["reason"], card["autopilot_activity"]) == ("waiting_for_you", "your_turn", None)


BLOCKERS = {
    "chat autonomy is copilot": (lambda client, card_id: autonomy(client, "copilot"), {}),
    "all apps are paused": (lambda client, card_id: client.post("/autopilot/pause"), {}),
    "the app is paused": (lambda client, card_id: client.post("/autopilot/pause", params={"app": "tinder"}), {}),
    "the AI budget is reached": (lambda client, card_id: client.put("/budget", json={"cap_usd": 0}), {}),
    "the app has no connector": (lambda client, card_id: None, {"app": "hinge"}),
    "the card is not linked to a match": (lambda client, card_id: None, {"external_id": None}),
    "the user took the chat over": (lambda client, card_id: client.post(f"/cards/{card_id}/take-over"), {}),
}


@pytest.mark.parametrize("blocker", BLOCKERS)
def test_a_chat_autopilot_cannot_act_on_waits_for_them(client, user_id, blocker):  # noqa: F811
    block, fields = BLOCKERS[blocker]
    autonomy(client, "autopilot")
    linked(client, "Kim", "match-kim")  # autopilot can act on Kim: a blocker of Ada's card alone stays hers
    card_id = new_card(client, "Ada", **{"app": "tinder", "external_id": "match-ada"} | fields)
    message(client, card_id, "me")

    block(client, card_id)

    card = placed(client, "Ada")
    assert (card["pipeline_group"], card["reason"], card["autopilot_activity"]) == ("waiting_for_them", None, None)


# Texting off-app and Archived.


def test_cards_from_number_swapped_on_are_texting_off_app(client):
    for stage in ("number_swapped", "date_set", "seeing_them"):
        new_card(client, stage, stage=stage)
    client.patch(f"/cards/{new_card(client, 'dated', stage='dated')}", json={"date_rating": 4})

    assert sorted(pipeline(client)["texting_off_app"]) == ["date_set", "dated", "number_swapped", "seeing_them"]
    assert list(pipeline(client)) == ["texting_off_app"]


def test_an_archived_card_waits_for_you_while_a_reason_applies_and_is_archived_otherwise(client):
    """Waiting for you wins over Archived, as the spec's group order says (owner, 2026-11-25)."""
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    new_card(client, "Ada", stage="archived", next_action="Return her book", due_date=yesterday)
    new_card(client, "Kim", stage="archived")

    ada, kim = placed(client, "Ada"), placed(client, "Kim")

    assert (ada["pipeline_group"], ada["reason"]) == ("waiting_for_you", "overdue")
    assert (kim["pipeline_group"], kim["reason"]) == ("archived", None)


# Order inside a group, and every card response.


def test_inside_a_group_hot_leads_come_first_then_the_most_recent_activity(client):
    old, recent, quiet, hot = (new_card(client, name) for name in ("Old", "Recent", "Quiet", "Hot"))
    message(client, old, "me", sent_at=ago(days=2))
    message(client, recent, "me", sent_at=ago(minutes=10))
    message(client, hot, "them", sent_at=ago(minutes=50))  # the match replied within the hour: a hot lead
    message(client, hot, "me", sent_at=ago(minutes=45))
    # Quiet has no messages: its activity is its last stage change, just now.

    assert pipeline(client) == {"waiting_for_them": ["Hot", "Quiet", "Recent", "Old"]}


def test_every_card_response_carries_its_pipeline_group_and_reason(client):
    card_id = new_card(client, "Ada", stage="matched")

    card = client.get(f"/cards/{card_id}").json()

    assert (card["pipeline_group"], card["reason"], card["autopilot_activity"]) == ("waiting_for_you", "opener_due", None)
