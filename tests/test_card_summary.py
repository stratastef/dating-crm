"""The card summary: what every card response carries so a row needs no other call (spec #44)."""

from tests.test_drafts import drafted, write_profile
from tests.test_review import card_with_reply


def card(client, card_id: int) -> dict:
    """The card as `GET /cards` lists it."""
    return next(listed for listed in client.get("/cards").json() if listed["id"] == card_id)


def test_a_cards_summary_carries_its_newest_message_whoever_sent_it(client):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Ada"}).json()["id"]
    assert card(client, card_id)["last_message"] is None

    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "hey", "sent_at": "2026-11-20T10:05:00Z"})
    # Added later, but sent earlier: the newest is by sent time.
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "hi!", "sent_at": "2026-11-20T10:00:00Z"})
    assert card(client, card_id)["last_message"] == {"sender": "me", "body": "hey", "sent_at": "2026-11-20T10:05:00Z"}

    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "saturday?", "sent_at": "2026-11-20T11:00:00Z"})
    assert card(client, card_id)["last_message"]["sender"] == "them"
    assert card(client, card_id)["last_message"]["body"] == "saturday?"


def test_a_cards_summary_cuts_the_last_message_to_its_first_100_characters(client):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Ada"}).json()["id"]
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "ha" * 80})

    assert card(client, card_id)["last_message"]["body"] == "ha" * 50


def test_a_cards_hot_lead_state_and_pending_draft_agree_with_the_review_queue(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    hot = card_with_reply(client, "Ada", minutes_ago=5)
    cold = card_with_reply(client, "Kim", minutes_ago=90)
    quiet = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    client.post(f"/cards/{hot}/drafts")
    client.post(f"/cards/{cold}/drafts")

    queue = {item["card_id"]: item for item in client.get("/queue").json()}

    for card_id in (hot, cold):
        assert card(client, card_id)["hot"] == queue[card_id]["hot"]
        assert card(client, card_id)["pending_draft"] == queue[card_id]["draft"]
    assert [card(client, card_id)["hot"] for card_id in (hot, cold)] == [True, False]
    assert card(client, quiet)["pending_draft"] is None


def test_a_card_with_no_photo_has_a_null_lead_photo_url_and_otherwise_its_first_photo(client):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Ada"}).json()["id"]
    assert card(client, card_id)["lead_photo_url"] is None

    client.post(f"/cards/{card_id}/photos", json={"url": "https://photos.test/ada-1.jpg"})
    client.post(f"/cards/{card_id}/photos", json={"url": "https://photos.test/ada-2.jpg"})

    assert card(client, card_id)["lead_photo_url"] == "https://photos.test/ada-1.jpg"


def test_a_card_added_by_hand_is_in_the_pipeline_and_search_by_name_finds_it_with_its_summary(client):
    """A match on an app without a connector: no external ID, nothing synced."""
    card_id = client.post("/cards", json={"app": "feeld", "name": "Ada Lovelace", "stage": "chatting"}).json()["id"]

    listed = card(client, card_id)
    found = client.get("/people", params={"q": "lovel"}).json()

    assert (listed["name"], listed["stage"], listed["last_message"], listed["hot"]) == ("Ada Lovelace", "chatting", None, False)
    assert found == [listed]


def test_a_cards_topic_comes_from_its_latest_draft(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = card_with_reply(client, "Ada", minutes_ago=5)

    llm.reply = drafted("the tate or the british museum", topic="museums")
    client.post(f"/cards/{card_id}/drafts")
    assert card(client, card_id)["topic"] == "museums"

    llm.reply = drafted("lisbon in may?", topic="her trip to lisbon")
    client.post(f"/cards/{card_id}/drafts")
    assert card(client, card_id)["topic"] == "her trip to lisbon"


def test_writing_a_draft_makes_no_extra_model_call_for_the_topic(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = card_with_reply(client, "Ada", minutes_ago=5)
    calls = len(llm.prompts)

    llm.reply = drafted("the tate or the british museum", topic="museums")
    client.post(f"/cards/{card_id}/drafts")

    assert len(llm.prompts) == calls + 1
    assert card(client, card_id)["topic"] == "museums"


def test_a_card_with_no_draft_yet_has_an_empty_topic(app, client, llm):
    card_id = card_with_reply(client, "Ada", minutes_ago=5)

    assert card(client, card_id)["topic"] == ""
    assert client.get("/pipeline").json()[0]["cards"][0]["topic"] == ""
