"""The feedback loop: outcome labels, edits, ratings and manual swipes change later prompts and retrieval."""

import json

from fastapi.testclient import TestClient

from tests.test_drafts import drafted, write_profile
from tests.test_swipes import signed_in, suggestions, tinder  # noqa: F401  (fixtures)
from tests.test_voice import chat, run_jobs


def test_a_chat_stays_labelled_as_led_to_a_date_after_the_card_is_archived(client):
    never = chat(client, "Max", "chatting", "hi", "hello")
    dated = chat(client, "Sam", "chatting", "hi", "hello")
    assert client.get(f"/cards/{dated}").json()["led_to_date"] is False

    client.patch(f"/cards/{dated}", json={"stage": "date_set"})
    archived = client.patch(f"/cards/{dated}", json={"stage": "archived", "date_rating": 2}).json()

    assert (archived["led_to_date"], archived["date_rating"]) == (True, 2)
    assert client.get(f"/cards/{never}").json()["led_to_date"] is False


def test_of_two_similar_past_chats_the_one_that_led_to_a_good_date_is_retrieved_first(client):
    lines = ("do you go bouldering much?", "every week, the climbing gym is home")
    good = chat(client, "Sam", "dated", *lines)
    bad = chat(client, "Jo", "dated", *lines)
    current = chat(client, "Alex", "chatting", "i saw you like bouldering", "yes! which climbing gym?")

    def found(limit=3):
        return client.get(f"/cards/{current}/similar-chats?limit={limit}").json()

    assert [past["card_id"] for past in found()] == [bad, good]  # equally similar: the newer card first
    client.patch(f"/cards/{bad}", json={"date_rating": 2})
    # Archived after the date: still a chat that led to a date.
    client.patch(f"/cards/{good}", json={"date_rating": 5, "stage": "archived"})

    assert [past["card_id"] for past in found()] == [good, bad]
    assert [(past["card_id"], past["date_rating"]) for past in found(limit=1)] == [(good, 5)]


def test_an_edit_of_a_draft_rewrites_the_style_profile_from_what_the_user_changed(app, client, llm):
    write_profile(app, client, llm, "Formal and long.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    llm.replies = [drafted("Good evening, Samantha! How are you?"), drafted("An unedited draft.")]
    draft_id = client.post(f"/cards/{card_id}/drafts").json()["id"]
    client.post(f"/cards/{card_id}/drafts")
    run_jobs(app)
    calls = len(llm.prompts)

    llm.reply = "Short, lowercase, no greetings."
    client.patch(f"/drafts/{draft_id}", json={"edited": "hey sam"})
    run_jobs(app)

    assert len(llm.prompts) == calls + 1
    edits = llm.prompts[-1].split("<my_edits>")[1].split("</my_edits>")[0]
    assert "draft: Good evening, Samantha! How are you?\nsent instead: hey sam" in edits
    assert "An unedited draft." not in llm.prompts[-1]
    assert "edit" in llm.systems[-1]
    assert client.get("/voice").json()["profile"] == "Short, lowercase, no greetings."


def test_manual_swipes_that_disagree_with_the_screen_and_date_ratings_change_the_next_screening_prompt(
    signed_in, llm, monkeypatch
):
    monkeypatch.setattr("app.swipes.BATCH", 1)  # one new profile per request: Dana, then Eve, then Fay
    llm.reply = "pass\nShe smokes."
    dana = suggestions(signed_in)["Dana"]
    assert "<manual_swipes>\n</manual_swipes>" in llm.prompts[-1]
    assert "<rated_dates>\n</rated_dates>" in llm.prompts[-1]

    signed_in.post(f"/swipes/{dana['id']}/decision", json={"decision": "like"})  # the user overrides the screen
    card_id = signed_in.post("/cards", json={"app": "tinder", "name": "Kim", "notes": "paints, has two cats"}).json()["id"]
    signed_in.patch(f"/cards/{card_id}", json={"date_rating": 5, "date_note": "talked for hours"})
    unrated = signed_in.post("/cards", json={"app": "tinder", "name": "Lou", "notes": "UNRATED"}).json()["id"]
    eve = suggestions(signed_in)["Eve"]

    prompt = llm.prompts[-1]
    assert "share long hikes" in prompt.split("<profile>")[1]  # Eve is the one screened
    swipes = prompt.split("<manual_swipes>")[1].split("</manual_swipes>")[0]
    assert "screen said pass, user chose like: Coffee first. I smoke a pack a day and love it." in swipes
    dates = prompt.split("<rated_dates>")[1].split("</rated_dates>")[0]
    assert "rated 5 of 5: paints, has two cats. talked for hours" in dates
    assert unrated and "UNRATED" not in prompt

    # A swipe that agrees with the screen says nothing new, so it is not repeated to the screen.
    signed_in.post(f"/swipes/{eve['id']}/decision", json={"decision": "pass"})
    suggestions(signed_in)
    assert "share long hikes" not in llm.prompts[-1]


def export(client) -> list[dict]:
    response = client.get("/feedback/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines()]  # one example per line


def test_the_labelled_data_is_exported_one_example_per_line_and_only_to_its_owner(app, signed_in, client_for, llm):
    bob = client_for("bob@example.com")
    llm.reply = "pass\nShe smokes."
    dana = suggestions(signed_in)["Dana"]
    signed_in.post(f"/swipes/{dana['id']}/decision", json={"decision": "like"})
    chat(bob, "Kim", "dated", "greetings from bob")
    card_id = chat(signed_in, "Zelda Quixote", "dated", "quixote here, come climb", "saturday?")
    signed_in.patch(f"/cards/{card_id}", json={"date_rating": 4})
    write_profile(app, signed_in, llm, "Short.")
    llm.reply = drafted("Dear Quixote, shall we?")
    draft_id = signed_in.post(f"/cards/{card_id}/drafts").json()["id"]
    signed_in.patch(f"/drafts/{draft_id}", json={"edited": "quixote, again?"})

    assert export(signed_in) == [
        {
            "type": "chat",
            "app": "tinder",
            "led_to_date": True,
            "date_rating": 4,
            "good_date": True,
            "messages": [
                {"sender": "them", "body": "quixote here, come climb"},
                {"sender": "me", "body": "saturday?"},
            ],
        },
        {"type": "draft_edit", "kind": "reply", "original": "Dear Quixote, shall we?", "edited": "quixote, again?"},
        {
            "type": "swipe",
            "app": "tinder",
            "bio": "Coffee first. I smoke a pack a day and love it.",
            "suggestion": "pass",
            "decision": "like",
        },
    ]
    assert [example["type"] for example in export(bob)] == ["chat"]
    assert TestClient(app).get("/feedback/export").status_code == 401

    purged = signed_in.post(
        "/people/purge", json={"card_ids": [card_id], "candidate_ids": [dana["id"]], "confirm": "purge"}
    )
    assert purged.status_code == 200
    assert signed_in.get("/feedback/export").text == ""  # nothing of a purged person is exported
