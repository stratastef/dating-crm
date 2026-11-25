import json

from app.jobs import run_once

PNG = b"\x89PNG\r\n\x1a\n not a real picture; the stub never looks at it"


def write_profile(app, client, llm):
    llm.reply = "Short, lowercase, teasing."
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    while run_once(app.state.engine):
        pass


def share(client, llm, read, draft="both. badly.", image=PNG, content_type="image/png"):
    """Upload a screenshot. `read` is what Claude sees in it; `draft` is what Claude then writes."""
    llm.replies = [read if isinstance(read, str) else json.dumps(read), draft]
    return client.post("/screenshots", content=image, headers={"Content-Type": content_type})


def chat(client, card_id):
    return [(m["sender"], m["body"]) for m in client.get(f"/cards/{card_id}/messages").json()]


def test_a_shared_screenshot_becomes_a_new_card_with_its_messages_and_a_draft(app, client, llm):
    write_profile(app, client, llm)

    response = share(
        client,
        llm,
        {
            "app": "Hinge",
            "name": "Sam",
            "messages": [
                {"sender": "me", "body": "is biscuit accepting visitors"},
                {"sender": "them", "body": "do you climb indoors or outdoors"},
            ],
        },
        draft="both. badly.",
    )

    assert response.status_code == 201
    draft = response.json()
    assert draft["kind"] == "reply" and draft["original"] == "both. badly."
    card = client.get(f"/cards/{draft['card_id']}").json()
    assert (card["app"], card["name"], card["stage"]) == ("hinge", "Sam", "chatting")
    assert chat(client, card["id"]) == [
        ("me", "is biscuit accepting visitors"),
        ("them", "do you climb indoors or outdoors"),
    ]
    assert llm.images == [("image/png", PNG)]  # Claude was sent the picture itself
    assert "them: do you climb indoors or outdoors" in llm.prompts[-1]  # the draft is written from what was read


def test_a_screenshot_of_a_known_match_adds_only_the_new_messages_to_their_card(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    write_profile(app, alice, llm)
    bob.post("/cards", json={"app": "hinge", "name": "Sam"})  # someone else's Sam is never matched
    card_id = alice.post("/cards", json={"app": "hinge", "name": "Sam", "notes": "Has a dog"}).json()["id"]
    alice.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "is biscuit accepting visitors"})
    alice.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "haha"})

    response = share(
        alice,
        llm,
        {
            "app": "hinge",
            "name": "sam",
            "messages": [
                {"sender": "them", "body": "haha"},
                {"sender": "them", "body": "haha"},
                {"sender": "me", "body": "saturday?"},
            ],
        },
    )

    assert response.json()["card_id"] == card_id
    assert len(alice.get("/cards").json()) == 1
    assert alice.get(f"/cards/{card_id}").json()["notes"] == "Has a dog"
    assert chat(alice, card_id) == [
        ("me", "is biscuit accepting visitors"),
        ("them", "haha"),
        ("them", "haha"),
        ("me", "saturday?"),
    ]


def test_a_profile_screenshot_with_no_messages_gets_an_opener(app, client, llm):
    write_profile(app, client, llm)

    draft = share(client, llm, {"app": "tinder", "name": "Kim", "messages": []}, draft="hi kim").json()

    assert draft["kind"] == "opener" and draft["original"] == "hi kim"
    assert client.get(f"/cards/{draft['card_id']}").json()["stage"] == "matched"


def test_an_upload_that_is_not_a_png_or_jpeg_or_is_too_large_is_refused_before_claude_sees_it(app, client, llm):
    write_profile(app, client, llm)
    calls = len(llm.prompts)
    read = {"app": "hinge", "name": "Sam", "messages": []}

    assert share(client, llm, read, content_type="application/pdf").status_code == 415
    assert share(client, llm, read, image=b"").status_code == 422
    assert share(client, llm, read, image=b"x" * (5 * 1024 * 1024 + 1)).status_code == 413
    assert len(llm.prompts) == calls
    assert share(client, llm, read, content_type="image/jpeg").status_code == 201


def test_a_screenshot_claude_cannot_read_is_reported_and_stores_nothing(app, client, llm):
    write_profile(app, client, llm)

    assert share(client, llm, "I can't tell what this is.").status_code == 502
    assert share(client, llm, {"app": "hinge", "name": "", "messages": []}).status_code == 502
    assert client.get("/cards").json() == []


def test_a_screenshot_needs_a_token(app):
    from fastapi.testclient import TestClient

    assert TestClient(app).post("/screenshots", content=PNG, headers={"Content-Type": "image/png"}).status_code == 401
