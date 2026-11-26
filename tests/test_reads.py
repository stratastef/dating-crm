import json

from app.jev import JevUnavailable
from tests.test_drafts import drafted, write_profile


def inference(kind, value, **changes):
    """One inference as Claude replies it; `changes` overrides a field."""
    return {
        "kind": kind,
        "value": value,
        "evidence": f"evidence for {value}",
        "confidence": 0.7,
        "about": "match",
        "protected_trait": None,
        "targets_insecurity": False,
    } | changes


def new_card(client):
    return client.post("/cards", json={"app": "hinge", "name": "Sam", "notes": "Has a dog called Biscuit"}).json()["id"]


def read(client, llm, card_id, inferences):
    llm.reply = json.dumps(inferences)
    return client.post(f"/cards/{card_id}/read")


def kinds(response):
    return [row["kind"] for row in response.json()]


def test_a_read_stores_each_inference_with_its_evidence_and_confidence(client, llm):
    card_id = new_card(client)
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "biscuit says hi!! come climb with us"})

    made = read(
        client,
        llm,
        card_id,
        [
            inference("interests", "climbing, dogs", evidence="'come climb with us'", confidence=0.9),
            inference("tone", "playful", evidence="double exclamation marks", confidence=0.6),
        ],
    )

    assert made.status_code == 200
    stored = client.get(f"/cards/{card_id}/read").json()
    assert stored == made.json()
    assert stored == [
        {
            "id": stored[0]["id"],
            "card_id": card_id,
            "kind": "interests",
            "value": "climbing, dogs",
            "evidence": "'come climb with us'",
            "confidence": 0.9,
            "corrected": None,
            "confidence_word": "Sure",
        },
        {
            "id": stored[1]["id"],
            "card_id": card_id,
            "kind": "tone",
            "value": "playful",
            "evidence": "double exclamation marks",
            "confidence": 0.6,
            "corrected": None,
            "confidence_word": "Likely",
        },
    ]
    prompt = llm.prompts[-1]
    assert "Has a dog called Biscuit" in prompt and "them: biscuit says hi!! come climb with us" in prompt
    assert llm.images[-1] == []  # no photos on the card: the read is from text only


def test_an_inference_is_sure_from_0_8_likely_from_0_5_and_otherwise_a_guess(client, llm):
    card_id = new_card(client)
    read(
        client,
        llm,
        card_id,
        [
            inference("texting_style", "short", confidence=0.8),
            inference("interests", "climbing", confidence=0.79),
            inference("values", "family", confidence=0.5),
            inference("tone", "playful", confidence=0.49),
        ],
    )

    stored = client.get(f"/cards/{card_id}/read").json()
    assert [(row["confidence"], row["confidence_word"]) for row in stored] == [
        (0.8, "Sure"),
        (0.79, "Likely"),
        (0.5, "Likely"),
        (0.49, "Guess"),
    ]


def test_a_correction_overrides_the_inference_and_survives_the_next_read(client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = new_card(alice)
    tone, interests = read(alice, llm, card_id, [inference("tone", "bold"), inference("interests", "climbing")]).json()

    assert bob.patch(f"/inferences/{tone['id']}", json={"corrected": "bob was here"}).status_code == 404
    assert bob.get(f"/cards/{card_id}/read").status_code == 404
    corrected = alice.patch(f"/inferences/{tone['id']}", json={"corrected": "sincere"})

    assert corrected.status_code == 200
    assert corrected.json()["value"] == "bold" and corrected.json()["corrected"] == "sincere"
    again = read(alice, llm, card_id, [inference("tone", "playful"), inference("values", "family")]).json()
    assert {row["kind"]: (row["value"], row["corrected"]) for row in again} == {
        "tone": ("playful", "sincere"),  # Claude's new guess is kept next to the correction, which still wins
        "values": ("family", None),  # the uncorrected `interests` inference is replaced by the new read
    }


def test_protected_trait_guesses_are_dropped_unless_the_user_opted_in(client, llm):
    card_id = new_card(client)
    guesses = [
        inference("religion", "Catholic"),
        inference("ethnicity", "Italian"),
        inference("health", "asthma"),
        inference("sexuality", "bisexual"),
        inference("politics", "left-leaning"),
        inference("values", "goes to mass every Sunday", protected_trait="religion"),
        inference("interests", "climbing"),
    ]

    assert client.get("/settings/protected-trait-guesses").json() == {"enabled": False}  # off unless opted in
    assert kinds(read(client, llm, card_id, guesses)) == ["interests"]
    assert "Do not make such guesses" in llm.systems[-1]

    assert client.put("/settings/protected-trait-guesses", json={"enabled": True}).status_code == 200
    assert sorted(kinds(read(client, llm, card_id, guesses))) == [
        "ethnicity", "health", "interests", "politics", "religion", "sexuality", "values",
    ]  # fmt: skip

    client.put("/settings/protected-trait-guesses", json={"enabled": False})
    assert kinds(client.get(f"/cards/{card_id}/read")) == ["interests"]  # opting out hides what was stored


def test_other_people_in_photos_are_never_stored_as_inferences(client, llm):
    card_id = new_card(client)

    made = read(
        client,
        llm,
        card_id,
        [
            inference("photos", "outdoors, with two friends, hiking gear, relaxed pose"),
            inference("interests", "her friend on the left likes sailing", about="other"),
            inference("friend", "the man beside her looks protective"),  # not a kind the read can hold
            {"kind": "values", "value": "her sister is ambitious", "evidence": "photo 2", "confidence": 0.5},  # no `about`
        ],
    )

    assert kinds(made) == ["photos"]
    assert "never who they are" in llm.systems[-1]


def test_an_inference_that_targets_an_insecurity_is_never_stored(client, llm):
    card_id = new_card(client)

    made = read(
        client,
        llm,
        card_id,
        [
            inference("values", "afraid of being alone, press on it", targets_insecurity=True),
            inference("insecurities", "her weight"),
            inference("tone", "sincere"),
        ],
    )

    assert kinds(made) == ["tone"]
    assert "Never infer insecurities" in llm.systems[-1]


def test_an_inference_claude_mislabelled_is_dropped_by_the_independent_check(client, llm, jev):
    """Claude's own `about`, `protected_trait` and `targets_insecurity` labels all say these are fine."""
    card_id = new_card(client)
    jev.yes = {
        "about_other_person": ["her sister"],
        "guesses_protected_trait": ["mass"],
        "targets_insecurity": ["ashamed"],
    }

    made = read(
        client,
        llm,
        card_id,
        [
            inference("values", "her sister is ambitious"),
            inference("interests", "goes to mass every Sunday"),
            inference("texting_style", "short replies", evidence="ashamed of her job, so press on it"),
            inference("tone", "sincere"),
        ],
    )

    assert kinds(made) == ["tone"]


def test_an_unlabelled_protected_guess_is_kept_only_while_the_user_is_opted_in(client, llm, jev):
    card_id = new_card(client)
    jev.yes["guesses_protected_trait"] = ["mass"]
    client.put("/settings/protected-trait-guesses", json={"enabled": True})

    assert kinds(read(client, llm, card_id, [inference("interests", "goes to mass every Sunday")])) == ["interests"]

    client.put("/settings/protected-trait-guesses", json={"enabled": False})
    assert kinds(client.get(f"/cards/{card_id}/read")) == []


def test_no_inference_is_stored_when_the_independent_check_cannot_be_asked(client, llm, monkeypatch):
    def down(sentence, check, subject=""):
        raise JevUnavailable("down")

    monkeypatch.setattr("app.jev.ask", down)
    card_id = new_card(client)

    assert kinds(read(client, llm, card_id, [inference("tone", "sincere")])) == []


def test_a_draft_that_plays_on_an_insecurity_hits_the_guardrail(app, client, llm, jev):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = new_card(client)
    jev.yes["plays_on_insecurity"] = ["nobody else"]

    llm.reply = drafted("nobody else will put up with you")
    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert draft["guardrail"] == ["plays_on_insecurity"]


def test_inferences_without_evidence_or_a_valid_confidence_are_dropped_and_a_non_json_reply_is_reported(client, llm):
    card_id = new_card(client)

    made = read(
        client,
        llm,
        card_id,
        [inference("tone", "bold", evidence=""), inference("values", "family", confidence=1.4), inference("interests", "dogs")],
    )
    assert kinds(made) == ["interests"]

    llm.reply = "She seems nice."
    assert client.post(f"/cards/{card_id}/read").status_code == 502
    assert kinds(client.get(f"/cards/{card_id}/read")) == ["interests"]  # the last read is kept


def test_a_read_looks_at_the_photos_attached_to_the_card(client_for, llm):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    card_id = new_card(alice)

    assert bob.post(f"/cards/{card_id}/photos", json={"url": "https://cdn.example/1.jpg"}).status_code == 404
    assert alice.post(f"/cards/{card_id}/photos", json={"url": "file:///etc/passwd"}).status_code == 422
    assert alice.post(f"/cards/{card_id}/photos", json={"url": "https://cdn.example/1.jpg"}).status_code == 201
    alice.post(f"/cards/{card_id}/photos", json={"url": "https://cdn.example/2.jpg"})
    read(alice, llm, card_id, [inference("photos", "beach, alone, sundress")])

    assert llm.images[-1] == ["https://cdn.example/1.jpg", "https://cdn.example/2.jpg"]


def test_a_draft_takes_its_tone_from_the_read_and_from_the_users_correction_of_it(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = new_card(client)
    tone = read(client, llm, card_id, [inference("tone", "bold"), inference("interests", "climbing")]).json()[0]

    llm.reply = drafted("race you up the wall")
    client.post(f"/cards/{card_id}/drafts")
    assert "tone: bold" in llm.prompts[-1] and "interests: climbing" in llm.prompts[-1]
    assert "tone" in llm.systems[-1]
    assert "insecurities" in llm.systems[-1]  # the draft is told never to use them

    client.patch(f"/inferences/{tone['id']}", json={"corrected": "sincere"})
    client.post(f"/cards/{card_id}/drafts")
    assert "tone: sincere" in llm.prompts[-1] and "tone: bold" not in llm.prompts[-1]


def test_a_draft_never_sees_an_inference_the_read_dropped(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = new_card(client)
    read(
        client,
        llm,
        card_id,
        [inference("values", "ashamed of her job", targets_insecurity=True), inference("religion", "Catholic")],
    )

    llm.reply = drafted("hi")
    client.post(f"/cards/{card_id}/drafts")

    assert "ashamed" not in llm.prompts[-1] and "Catholic" not in llm.prompts[-1]
