from app.jobs import run_once


def run_jobs(app):
    while run_once(app.state.engine):
        pass


def test_the_style_profile_is_written_from_the_answers_and_the_users_own_messages(app, client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = alice.post("/cards", json={"app": "tinder", "name": "Sam"}).json()["id"]
    alice.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "fancy a climb on sunday?"})
    alice.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "only if you belay"})
    bobs_card = bob.post("/cards", json={"app": "tinder", "name": "Kim"}).json()["id"]
    bob.post(f"/cards/{bobs_card}/messages", json={"sender": "me", "body": "greetings from bob"})

    llm.reply = "Short, lowercase, teasing."
    alice.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    assert alice.get("/voice").json()["profile"] is None
    run_jobs(app)

    assert alice.get("/voice").json()["profile"] == "Short, lowercase, teasing."
    prompt = next(prompt for prompt in llm.prompts if "greetings from bob" not in prompt)
    assert "Emoji?" in prompt and "Never" in prompt
    assert "fancy a climb on sunday?" in prompt
    assert "only if you belay" not in prompt
    assert len(llm.prompts) == 2  # one for alice, one for bob


def test_the_style_profile_is_rewritten_when_a_new_chat_message_of_the_user_arrives(app, client, llm):
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    run_jobs(app)
    card_id = client.post("/cards", json={"app": "hinge", "name": "Alex"}).json()["id"]

    llm.reply = "Now also dry."
    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "i only date people with libraries"})
    run_jobs(app)

    voice = client.get("/voice").json()
    assert (voice["answers"], voice["profile"]) == ({"Emoji?": "Never"}, "Now also dry.")
    assert "i only date people with libraries" in llm.prompts[-1]


def test_many_new_messages_queue_one_profile_rewrite(app, client, llm):
    card_id = client.post("/cards", json={"app": "hinge", "name": "Alex"}).json()["id"]

    for body in ["one", "two", "three"]:
        client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": body})
    run_jobs(app)

    assert len(llm.prompts) == 1


def chat(client, name, stage, *bodies):
    card_id = client.post("/cards", json={"app": "tinder", "name": name, "stage": stage}).json()["id"]
    for index, body in enumerate(bodies):
        client.post(f"/cards/{card_id}/messages", json={"sender": "me" if index % 2 else "them", "body": body})
    return card_id


def test_past_chats_that_led_to_a_date_are_found_by_similarity_to_a_conversation(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    climbing = chat(alice, "Sam", "dated", "do you go bouldering much?", "every week, the climbing gym is home")
    cooking = chat(alice, "Jo", "date_set", "what do you cook on sundays?", "ramen from scratch, it takes all day")
    chat(alice, "Max", "chatting", "bouldering or climbing with ropes?", "bouldering at the climbing gym")
    chat(bob, "Kim", "dated", "is bouldering at the climbing gym hard?", "come and see")
    current = chat(alice, "Alex", "chatting", "i saw you like bouldering", "yes! which climbing gym do you go to?")

    found = alice.get(f"/cards/{current}/similar-chats")

    assert found.status_code == 200
    assert [past["card_id"] for past in found.json()] == [climbing, cooking]
    assert found.json()[0]["messages"] == [
        {"sender": "them", "body": "do you go bouldering much?"},
        {"sender": "me", "body": "every week, the climbing gym is home"},
    ]
    assert [past["card_id"] for past in alice.get(f"/cards/{current}/similar-chats?limit=1").json()] == [climbing]
    assert bob.get(f"/cards/{current}/similar-chats").status_code == 404


def test_questionnaire_answers_are_stored_per_user(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")

    saved = alice.put("/voice/questionnaire", json={"answers": {"How do you open?": "With a joke about their dog"}})

    assert saved.status_code == 200
    assert alice.get("/voice").json()["answers"] == {"How do you open?": "With a joke about their dog"}
    assert bob.get("/voice").json()["answers"] == {}
    assert bob.get("/voice").json()["profile"] is None


def test_the_questionnaire_questions_come_from_the_server_and_answering_them_writes_the_style_profile(app, client, llm):
    questions = client.get("/voice").json()["questions"]
    assert questions and all(isinstance(question, str) and question for question in questions)

    llm.reply = "Warm, short, asks questions back."
    saved = client.put("/voice/questionnaire", json={"answers": {question: "yes" for question in questions}})
    run_jobs(app)

    assert saved.json()["questions"] == questions
    assert client.get("/voice").json()["profile"] == "Warm, short, asks questions back."
    assert all(question in llm.prompts[-1] for question in questions)
