def test_a_created_card_can_be_read_back(client):
    created = client.post(
        "/cards",
        json={
            "app": "tinder",
            "name": "Sam",
            "notes": "climbs",
            "next_action": "ask about the trip",
            "due_date": "2026-12-01",
        },
    )

    assert created.status_code == 201
    card = client.get(f"/cards/{created.json()['id']}").json()
    assert card["app"] == "tinder"
    assert card["name"] == "Sam"
    assert card["stage"] == "matched"
    assert card["notes"] == "climbs"
    assert card["next_action"] == "ask about the trip"
    assert card["due_date"] == "2026-12-01"


def test_cards_are_private_to_their_owner(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = alice.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]

    assert bob.get(f"/cards/{card_id}").status_code == 404
    assert bob.patch(f"/cards/{card_id}", json={"notes": "mine now"}).status_code == 404
    assert bob.get("/cards").json() == []
    assert [card["name"] for card in alice.get("/cards").json()] == ["Sam"]


def test_updating_a_card_changes_only_the_fields_sent(client):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Alex", "notes": "likes jazz"}).json()["id"]

    updated = client.patch(f"/cards/{card_id}", json={"next_action": "send playlist", "due_date": "2026-12-05"})

    assert updated.status_code == 200
    card = client.get(f"/cards/{card_id}").json()
    assert card["next_action"] == "send playlist"
    assert card["due_date"] == "2026-12-05"
    assert card["notes"] == "likes jazz"
    assert client.patch(f"/cards/{card_id}", json={"due_date": None}).json()["due_date"] is None
    assert client.patch(f"/cards/{card_id}", json={"name": None}).status_code == 422
    assert client.patch(f"/cards/{card_id}", json={}).json()["name"] == "Alex"


def test_the_card_list_filters_by_stage_and_app(client):
    client.post("/cards", json={"app": "tinder", "name": "Sam"})
    client.post("/cards", json={"app": "tinder", "name": "Jo", "stage": "chatting"})
    client.post("/cards", json={"app": "hinge", "name": "Alex", "stage": "chatting"})

    def names(**params):
        return [card["name"] for card in client.get("/cards", params=params).json()]

    assert names() == ["Sam", "Jo", "Alex"]
    assert names(stage="chatting") == ["Jo", "Alex"]
    assert names(app="tinder") == ["Sam", "Jo"]
    assert names(stage="chatting", app="tinder") == ["Jo"]
    assert client.get("/cards", params={"stage": "stalled"}).status_code == 422


def test_messages_are_kept_per_card_with_sender_and_time(client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]
    other_id = client.post("/cards", json={"app": "tinder", "name": "Jo"}).json()["id"]

    sent = client.post(
        f"/cards/{card_id}/messages",
        json={"sender": "them", "body": "hey you", "sent_at": "2026-11-20T18:30:00Z"},
    )
    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "hey!", "sent_at": "2026-11-20T18:45:00Z"})
    client.post(f"/cards/{other_id}/messages", json={"sender": "me", "body": "hi Jo"})

    assert sent.status_code == 201
    messages = client.get(f"/cards/{card_id}/messages").json()
    assert [(m["sender"], m["body"], m["sent_at"]) for m in messages] == [
        ("them", "hey you", "2026-11-20T18:30:00Z"),
        ("me", "hey!", "2026-11-20T18:45:00Z"),
    ]
    stamped = client.get(f"/cards/{other_id}/messages").json()
    assert [m["body"] for m in stamped] == ["hi Jo"]
    assert stamped[0]["sent_at"]  # defaults to now when the caller gives no time


def test_message_sender_must_be_me_or_them(client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]

    assert client.post(f"/cards/{card_id}/messages", json={"sender": "bot", "body": "hi"}).status_code == 422


def test_messages_are_private_to_the_cards_owner(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = alice.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]
    alice.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "secret"})

    assert bob.get(f"/cards/{card_id}/messages").status_code == 404
    assert bob.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "hi"}).status_code == 404
    assert [m["body"] for m in alice.get(f"/cards/{card_id}/messages").json()] == ["secret"]


def test_an_external_id_identifies_one_card_per_app_and_one_message_per_card(client):
    match = {"app": "tinder", "name": "Sam", "external_id": "t-123"}
    card_id = client.post("/cards", json=match).json()["id"]
    message = {"sender": "them", "body": "hey", "external_id": "m-1"}

    assert client.post("/cards", json=match).status_code == 409
    assert client.post("/cards", json={**match, "app": "hinge"}).status_code == 201
    assert client.post(f"/cards/{card_id}/messages", json=message).status_code == 201
    assert client.post(f"/cards/{card_id}/messages", json=message).status_code == 409


def test_a_card_moves_to_a_new_stage_and_records_when(client):
    card = client.post("/cards", json={"app": "hinge", "name": "Alex"}).json()

    moved = client.patch(f"/cards/{card['id']}", json={"stage": "chatting"}).json()

    assert moved["stage"] == "chatting"
    assert moved["stage_changed_at"] > card["stage_changed_at"]
    # A change that leaves the stage alone leaves the timestamp alone.
    noted = client.patch(f"/cards/{card['id']}", json={"notes": "replied fast", "stage": "chatting"}).json()
    assert noted["stage_changed_at"] == moved["stage_changed_at"]


def test_every_pipeline_stage_is_accepted_and_nothing_else(client):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Alex"}).json()["id"]

    for stage in ["matched", "chatting", "number_swapped", "date_set", "dated", "seeing_them", "archived"]:
        assert client.patch(f"/cards/{card_id}", json={"stage": stage}).json()["stage"] == stage
    assert client.patch(f"/cards/{card_id}", json={"stage": "stalled"}).status_code == 422
    assert client.post("/cards", json={"app": "hinge", "name": "Kim", "stage": "ghosted"}).status_code == 422
    assert client.post("/cards", json={"app": "hinge", "name": "Kim", "stage": "dated"}).json()["stage"] == "dated"


def test_a_dated_card_keeps_its_rating_and_note(client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam", "stage": "date_set"}).json()["id"]
    assert client.get(f"/cards/{card_id}").json()["date_rating"] is None

    rated = client.patch(f"/cards/{card_id}", json={"stage": "dated", "date_rating": 4, "date_note": "easy to talk to"})

    assert rated.status_code == 200
    card = client.get(f"/cards/{card_id}").json()
    assert card["stage"] == "dated"
    assert card["date_rating"] == 4
    assert card["date_note"] == "easy to talk to"
    assert client.patch(f"/cards/{card_id}", json={"date_rating": 0}).status_code == 422
    assert client.patch(f"/cards/{card_id}", json={"date_rating": 6}).status_code == 422


def test_a_rating_saved_without_a_stage_change_is_stored_and_counts_toward_good_dates(client):
    # A date synced into Dated: the rating sheet saves the rating and note, the stage stays as it was.
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam", "stage": "dated"}).json()["id"]

    rated = client.patch(f"/cards/{card_id}", json={"stage": "dated", "date_rating": 5, "date_note": "talked for hours"})

    assert rated.status_code == 200
    card = client.get(f"/cards/{card_id}").json()
    assert (card["stage"], card["date_rating"], card["date_note"], card["good_date"]) == (
        "dated", 5, "talked for hours", True,
    )  # fmt: skip
    assert [week["good_dates"] for week in client.get("/dashboard").json()["weeks"]] == [1]


def test_a_good_date_is_a_rating_of_4_or_5(client):
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam", "stage": "dated"}).json()["id"]

    def good_date(rating):
        return client.patch(f"/cards/{card_id}", json={"date_rating": rating}).json()["good_date"]

    assert client.get(f"/cards/{card_id}").json()["good_date"] is False
    assert [good_date(rating) for rating in (1, 2, 3, 4, 5)] == [False, False, False, True, True]
