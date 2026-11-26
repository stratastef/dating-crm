from datetime import UTC, datetime, timedelta

from tests.test_drafts import write_profile
from tests.test_swipe_autopilot import signed_in  # noqa: F401  (fixture)
from tests.test_swipes import tinder  # noqa: F401  (fixture)


def card_with_reply(client, name: str, minutes_ago: int) -> int:
    """A card whose match replied that many minutes ago."""
    card_id = client.post("/cards", json={"app": "hinge", "name": name}).json()["id"]
    sent_at = (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat()
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "saturday works", "sent_at": sent_at})
    return card_id


def test_a_draft_for_a_match_who_replied_within_the_hour_sends_a_push_at_once(app, client, llm, apns):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post("/devices", json={"token": "abc123"})
    card_id = card_with_reply(client, "Ada", minutes_ago=5)

    client.post(f"/cards/{card_id}/drafts")

    assert len(apns.sent) == 1
    assert apns.sent[0]["payload"]["card_id"] == card_id
    assert "Ada" in apns.sent[0]["payload"]["aps"]["alert"]["body"]


def test_a_draft_for_any_other_match_sends_no_push(app, client, llm, apns):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post("/devices", json={"token": "abc123"})
    cold = card_with_reply(client, "Kim", minutes_ago=90)
    opener = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    client.post(f"/cards/{cold}/drafts")
    client.post(f"/cards/{opener}/drafts")

    assert apns.sent == []


def test_a_card_in_date_coordination_is_a_hot_lead(app, client, llm, jev, apns):
    """The match's unanswered message is about when to meet. Nothing else makes this card hot."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post("/devices", json={"token": "abc123"})
    jev.yes["logistics"] = ["saturday"]
    card_id = card_with_reply(client, "Kim", minutes_ago=90)
    client.post(f"/cards/{card_id}/hand-back")  # the handover the message caused is over
    apns.sent.clear()

    client.post(f"/cards/{card_id}/drafts")

    assert len(apns.sent) == 1
    assert [item["hot"] for item in client.get("/queue").json()] == [True]


def test_the_queue_lists_pending_drafts_with_hot_leads_first(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    write_profile(app, alice, llm, "Short, lowercase, teasing.")
    cold = card_with_reply(alice, "Kim", minutes_ago=90)
    hot = card_with_reply(alice, "Ada", minutes_ago=5)
    llm.reply = "see you saturday"
    cold_draft = alice.post(f"/cards/{cold}/drafts").json()
    hot_draft = alice.post(f"/cards/{hot}/drafts").json()

    queue = alice.get("/queue")

    assert queue.status_code == 200
    assert [(item["kind"], item["hot"], item["card_id"], item["card_name"], item["draft"]) for item in queue.json()] == [
        ("draft", True, hot, "Ada", hot_draft),
        ("draft", False, cold, "Kim", cold_draft),
    ]
    assert bob.get("/queue").json() == []


def test_a_dismissed_draft_leaves_the_queue(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    write_profile(app, alice, llm, "Short, lowercase, teasing.")
    card_id = card_with_reply(alice, "Kim", minutes_ago=90)
    draft_id = alice.post(f"/cards/{card_id}/drafts").json()["id"]

    assert bob.post(f"/drafts/{draft_id}/dismiss").status_code == 404
    dismissed = alice.post(f"/drafts/{draft_id}/dismiss")

    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert alice.get("/queue").json() == []


def test_the_review_queue_lists_hot_leads_first_then_the_oldest_first_whatever_their_kind(app, signed_in, llm, jev):
    write_profile(app, signed_in, llm, "Short, lowercase, teasing.")
    signed_in.post(f"/cards/{card_with_reply(signed_in, 'Ada', minutes_ago=5)}/drafts")  # hot
    signed_in.post(f"/cards/{card_with_reply(signed_in, 'Kim', minutes_ago=90)}/drafts")
    llm.replies = ["pass\nNothing in common.", "super like\nShe climbs and wants kids."]  # Dana, then Eve
    signed_in.post("/swipes/tinder/suggestions")  # a paid item for Eve: never hot
    jev.yes["asks_if_ai"] = ["a bot"]
    sam = signed_in.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    signed_in.post(f"/cards/{sam}/messages", json={"sender": "them", "body": "are you a bot?"})  # a handover: hot

    queue = signed_in.get("/queue").json()

    assert [(item["kind"], item["card_name"], item["hot"]) for item in queue] == [
        ("draft", "Ada", True),
        ("handover", "Sam", True),
        ("draft", "Kim", False),
        ("paid_item", "Eve", False),
    ]


def test_a_reply_draft_carries_the_message_it_answers_and_an_opener_carries_none(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    kim = client.post("/cards", json={"app": "hinge", "name": "Kim"}).json()["id"]
    client.post(f"/cards/{kim}/photos", json={"url": "https://photos.test/kim-1.jpg"})
    for body, sent_at in [("do you climb?", "2026-11-20T10:00:00Z"), ("saturday works", "2026-11-20T10:05:00Z")]:
        client.post(f"/cards/{kim}/messages", json={"sender": "them", "body": body, "sent_at": sent_at})
    client.post(f"/cards/{kim}/messages", json={"sender": "me", "body": "great", "sent_at": "2026-11-20T10:06:00Z"})
    sam = client.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]
    client.post(f"/cards/{kim}/drafts")
    client.post(f"/cards/{sam}/drafts")
    # Written after the draft, so the draft does not answer it.
    client.post(f"/cards/{kim}/messages", json={"sender": "them", "body": "hello?"})

    items = {item["card_name"]: item for item in client.get("/queue").json()}

    assert items["Kim"]["draft"]["kind"] == "reply"
    assert items["Kim"]["message"] == {"body": "saturday works", "sent_at": "2026-11-20T10:05:00Z"}
    assert (items["Kim"]["card"]["app"], items["Kim"]["card"]["lead_photo_url"]) == ("hinge", "https://photos.test/kim-1.jpg")
    assert items["Sam"]["draft"]["kind"] == "opener"
    assert items["Sam"]["message"] is None
    assert (items["Sam"]["card"]["app"], items["Sam"]["card"]["lead_photo_url"]) == ("tinder", None)


def test_a_handover_item_carries_the_trigger_that_fired_and_the_quoted_message(client, jev):
    jev.yes["asks_if_ai"] = ["a bot"]
    sam = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    asked = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=2)
    for body, sent_at in [("haha", asked - timedelta(minutes=1)), ("are you a bot?", asked), ("??", asked + timedelta(minutes=1))]:
        client.post(f"/cards/{sam}/messages", json={"sender": "them", "body": body, "sent_at": sent_at.isoformat()})

    [item] = client.get("/queue").json()

    assert (item["kind"], item["card_name"], item["card"]["name"]) == ("handover", "Sam", "Sam")
    assert item["triggers"] == ["asks_if_ai"]
    assert item["message"] == {"body": "are you a bot?", "sent_at": asked.strftime("%Y-%m-%dT%H:%M:%SZ")}
