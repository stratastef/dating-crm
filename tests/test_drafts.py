import json

from app.jobs import run_once


def drafted(message: str, topic: str = "", **timing) -> str:
    """What Claude replies when it writes a draft: the message and the chat's topic. `timing` adds the send-time
    fields, `adjustment` and `timing_reason`."""
    return json.dumps({"message": message, "topic": topic, **timing})


def write_profile(app, client, llm, profile):
    """Write the user's style profile. Claude then replies `stub draft` to a draft, unless the test sets a reply."""
    llm.reply = profile
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    while run_once(app.state.engine):
        pass
    llm.reply = drafted("stub draft")


def test_a_card_with_no_messages_gets_an_opener_written_from_the_style_profile(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam", "notes": "Has a dog called Biscuit"}).json()["id"]

    llm.reply = drafted("is biscuit accepting visitors", timing_reason="a fresh match")
    draft = client.post(f"/cards/{card_id}/drafts")

    assert draft.status_code == 201
    body = draft.json()
    assert body == {
        "id": body["id"],
        "card_id": card_id,
        "kind": "opener",
        "status": "pending",
        "original": "is biscuit accepting visitors",
        "edited": None,
        "guardrail": [],
        "hot_lead": False,
        "sendable": False,  # Hinge has no connector
        "send_at": body["send_at"],  # when it is best sent: see `tests/test_send_timing.py`
        "timing_reason": "a fresh match",
        "created_at": body["created_at"],
    }
    assert body["send_at"]
    prompt = llm.prompts[-1]
    assert "opener" in prompt
    assert "Short, lowercase, teasing." in prompt
    assert "hinge" in prompt and "Sam" in prompt and "Has a dog called Biscuit" in prompt


def test_a_draft_is_written_with_the_preferences_in_force(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.put("/preferences", json={"wishes": "someone outdoorsy", "must_haves": ["wants kids"], "dealbreakers": []})
    client.put("/preferences", json={"wishes": "someone bookish", "must_haves": ["lives nearby"], "dealbreakers": []})
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    llm.reply = drafted("what are you reading")
    client.post(f"/cards/{card_id}/drafts")

    prompt = llm.prompts[-1]
    assert "someone bookish" in prompt and "lives nearby" in prompt
    assert "someone outdoorsy" not in prompt


def test_a_card_with_messages_gets_a_reply_written_from_the_conversation_and_similar_past_chats(app, client, llm):
    dated = client.post("/cards", json={"app": "tinder", "name": "Kim", "stage": "dated"}).json()["id"]
    client.post(f"/cards/{dated}/messages", json={"sender": "them", "body": "do you climb outdoors too"})
    client.post(f"/cards/{dated}/messages", json={"sender": "me", "body": "only when the rock is dry. saturday?"})
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]
    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "is biscuit accepting visitors"})
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "do you climb indoors or outdoors"})
    write_profile(app, client, llm, "Short, lowercase, teasing.")

    llm.reply = drafted("  both. badly.\n")
    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert draft["kind"] == "reply"
    assert draft["original"] == "both. badly."
    prompt = llm.prompts[-1]
    assert "reply" in prompt and "opener" not in prompt
    assert "Short, lowercase, teasing." in prompt
    assert "me: only when the rock is dry. saturday?" in prompt  # the past chat that led to a date
    assert prompt.index("me: is biscuit accepting visitors") < prompt.index("them: do you climb indoors or outdoors")


def test_the_users_edit_is_stored_next_to_the_original_draft(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    write_profile(app, alice, llm, "Short, lowercase, teasing.")
    card_id = alice.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    llm.reply = drafted("is biscuit accepting visitors")
    draft_id = alice.post(f"/cards/{card_id}/drafts").json()["id"]

    assert bob.patch(f"/drafts/{draft_id}", json={"edited": "bob was here"}).status_code == 404
    edited = alice.patch(f"/drafts/{draft_id}", json={"edited": "is biscuit taking visitors?"})

    assert edited.status_code == 200
    assert edited.json()["original"] == "is biscuit accepting visitors"
    assert edited.json()["edited"] == "is biscuit taking visitors?"
    assert edited.json()["status"] == "pending"


def test_a_draft_needs_the_users_own_card_and_a_style_profile(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = alice.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    assert alice.post(f"/cards/{card_id}/drafts").status_code == 409  # no style profile yet
    write_profile(app, bob, llm, "Formal.")
    calls = len(llm.prompts)
    assert bob.post(f"/cards/{card_id}/drafts").status_code == 404
    assert len(llm.prompts) == calls


def test_an_empty_reply_from_claude_is_reported_and_not_stored_as_a_draft(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    llm.reply = drafted("  \n")

    assert client.post(f"/cards/{card_id}/drafts").status_code == 502


def test_a_reply_from_claude_that_is_not_a_draft_is_reported_and_never_stored_as_one(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    for reply in ("is biscuit accepting visitors", '{"message": "is biscuit', '{"topic": "dogs"}'):
        llm.reply = reply
        assert client.post(f"/cards/{card_id}/drafts").status_code == 502

    assert client.get("/queue").json() == []


def test_a_draft_wrapped_in_a_code_fence_is_read_from_inside_it(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    llm.reply = f"```json\n{drafted('is biscuit accepting visitors', topic='her dog')}\n```"

    assert client.post(f"/cards/{card_id}/drafts").json()["original"] == "is biscuit accepting visitors"
