from datetime import datetime, timedelta, timezone

from app import handover
from app.cards import upsert_card, upsert_message
from app.jev import JevUnavailable


def card(client, name: str = "Sam") -> int:
    return client.post("/cards", json={"app": "hinge", "name": name}).json()["id"]


def incoming(client, card_id: int, body: str):
    return client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": body})


def paused(app, card_id: int) -> bool:
    with app.state.engine.begin() as db:
        return handover.is_paused(db, card_id)


def test_a_handover_hit_pauses_autopilot_for_that_card_only(app, client, jev):
    jev.yes["logistics"] = ["saturday"]
    hit, other = card(client, "Ada"), card(client, "Kim")

    incoming(client, hit, "Saturday at 8?")
    incoming(client, other, "do you climb outdoors too")

    assert paused(app, hit)
    assert not paused(app, other)
    assert client.get(f"/cards/{hit}").json()["handover"] == "pending"
    assert client.get(f"/cards/{other}").json()["handover"] is None


def test_a_hit_sends_a_push_with_the_suggested_replies(client, jev, llm, apns):
    jev.yes["logistics"] = ["saturday"]
    client.post("/devices", json={"token": "abc123"})
    card_id = card(client, "Ada")
    llm.reply = "saturday works\n\nhow about sunday instead\n"

    incoming(client, card_id, "Saturday at 8?")

    suggestions = ["saturday works", "how about sunday instead"]
    assert client.get(f"/cards/{card_id}").json()["handover_suggestions"] == suggestions
    assert "Saturday at 8?" in llm.prompts[-1]
    assert len(apns.sent) == 1
    payload = apns.sent[0]["payload"]
    assert payload["card_id"] == card_id
    assert "Ada" in payload["aps"]["alert"]["title"]
    assert payload["aps"]["alert"]["body"] == "saturday works\nhow about sunday instead"


def test_no_suggestion_for_a_bot_or_ai_question_denies_being_ai(client, jev, llm, apns):
    jev.yes = {"asks_if_ai": ["are you a bot"], "denies_ai": ["not a bot", "100% human"]}
    client.post("/devices", json={"token": "abc123"})
    card_id = card(client)
    llm.reply = "lol no, i am not a bot\nwould a bot be this bad at replying\ni'm 100% human, promise"

    incoming(client, card_id, "wait, are you a bot?")

    assert client.get(f"/cards/{card_id}").json()["handover_suggestions"] == ["would a bot be this bad at replying"]
    assert apns.sent[0]["payload"]["aps"]["alert"]["body"] == "would a bot be this bad at replying"


def test_no_suggestion_denies_being_ai_when_read_with_the_question_it_answers(client, jev, llm):
    """"Nope, why?" denies nothing on its own; as the answer to "are you a bot?" it is a flat denial."""
    jev.yes = {"asks_if_ai": ["are you a bot"], "answer_denies_ai": ["are you a bot? answer: nope"]}
    card_id = card(client)
    llm.reply = "Nope, why?\nwould a bot be this bad at replying"

    incoming(client, card_id, "wait, are you a bot?")

    assert client.get(f"/cards/{card_id}").json()["handover_suggestions"] == ["would a bot be this bad at replying"]


def test_the_chat_is_handed_over_without_suggestions_when_claude_or_jev_cannot_be_asked(
    app, client, jev, llm, apns, monkeypatch
):
    client.post("/devices", json={"token": "abc123"})
    jev.yes["logistics"] = ["saturday"]
    over_budget = card(client, "Ada")
    client.put("/budget", json={"cap_usd": 0})
    incoming(client, over_budget, "Saturday at 8?")

    client.put("/budget", json={"cap_usd": 50})
    no_jev = card(client, "Kim")

    def unavailable(sentence, check):
        raise JevUnavailable("down")

    monkeypatch.setattr("app.jev.ask", unavailable)
    incoming(client, no_jev, "hey")

    assert llm.prompts == []  # no Claude call for suggestions the guardrail could not check
    for card_id in (over_budget, no_jev):
        assert paused(app, card_id)
        assert client.get(f"/cards/{card_id}").json()["handover_suggestions"] == []
    assert len(apns.sent) == 2


def test_the_users_reply_ends_a_pending_handover(app, client, jev):
    jev.yes["logistics"] = ["saturday"]
    card_id = card(client)
    incoming(client, card_id, "Saturday at 8?")

    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "saturday works"})

    assert not paused(app, card_id)
    assert client.get(f"/cards/{card_id}").json()["handover_suggestions"] == []


def test_take_over_keeps_the_chat_manual_until_the_user_hands_it_back(app, client_for, jev):
    alice, bob = client_for("alice@example.com"), client_for("bob@example.com")
    jev.yes["logistics"] = ["saturday"]
    card_id = card(alice)
    incoming(alice, card_id, "Saturday at 8?")

    assert bob.post(f"/cards/{card_id}/take-over").status_code == 404
    taken = alice.post(f"/cards/{card_id}/take-over")
    alice.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "saturday works"})
    incoming(alice, card_id, "do you climb outdoors too")

    assert taken.json() == {"handover": "taken_over", "handover_suggestions": ["stub reply"]}
    assert paused(app, card_id)  # neither the user's reply nor a harmless message ends a take-over
    assert alice.get(f"/cards/{card_id}").json()["handover"] == "taken_over"

    assert bob.post(f"/cards/{card_id}/hand-back").status_code == 404
    back = alice.post(f"/cards/{card_id}/hand-back")

    assert back.json() == {"handover": None, "handover_suggestions": []}
    assert not paused(app, card_id)


def test_an_old_hit_from_a_first_sync_pauses_the_card_without_a_push_or_a_claude_call(app, client, jev, llm, apns):
    jev.yes["asks_if_ai"] = ["are you real"]
    client.post("/devices", json={"token": "abc123"})
    with app.state.engine.begin() as db:
        user_id = db.exec_driver_sql("SELECT id FROM users").scalar_one()
        answered = upsert_card(db, user_id, "tinder", "match-1", "Sam")
        upsert_message(db, user_id, answered, "m1", "them", "are you real", "2026-01-01T10:00:00Z")
        upsert_message(db, user_id, answered, "m2", "me", "ask me something", "2026-01-01T10:05:00Z")
        unanswered = upsert_card(db, user_id, "tinder", "match-2", "Kim")
        upsert_message(db, user_id, unanswered, "m1", "them", "are you real", "2026-01-01T10:00:00Z")

    assert not paused(app, answered)
    assert paused(app, unanswered)
    assert llm.prompts == []
    assert apns.sent == []


def test_a_pending_handover_is_a_hot_lead_in_the_queue_until_it_is_taken_over(client, jev, llm):
    jev.yes["logistics"] = ["saturday"]
    card_id = card(client, "Ada")
    llm.reply = "saturday works"
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()  # not hot as a recent reply
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "Saturday at 8?", "sent_at": old})

    assert client.get("/queue").json() == [
        {
            "kind": "handover",
            "hot": True,
            "card_id": card_id,
            "card_name": "Ada",
            "draft": None,
            "suggestions": ["saturday works"],
            "paid_item": None,
        }
    ]

    client.post(f"/cards/{card_id}/take-over")

    assert client.get("/queue").json() == []


def at(client, card_id: int, sender: str, body: str, sent_at: datetime) -> None:
    message = {"sender": sender, "body": body, "sent_at": sent_at.isoformat()}
    assert client.post(f"/cards/{card_id}/messages", json=message).status_code == 201


def test_a_hit_on_an_earlier_message_of_one_batch_pauses_the_card(app, client, jev):
    """Tinder returns the newest message first, so the one that asks is stored after the one that followed it."""
    jev.yes["asks_if_ai"] = ["are you a bot"]
    card_id = card(client)
    now = datetime.now(timezone.utc)

    at(client, card_id, "them", "??", now)
    at(client, card_id, "them", "are you a bot?", now - timedelta(minutes=1))

    assert paused(app, card_id)


def test_a_hit_on_a_message_the_user_already_answered_does_not_pause_the_card(app, client, jev):
    jev.yes["asks_if_ai"] = ["are you a bot"]
    card_id = card(client)
    now = datetime.now(timezone.utc)

    at(client, card_id, "me", "ask me anything", now)
    at(client, card_id, "them", "are you a bot?", now - timedelta(minutes=1))

    assert not paused(app, card_id)
