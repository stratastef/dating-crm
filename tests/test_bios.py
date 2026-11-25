import json

from app.jobs import run_once


def write_profile(app, client, llm, profile):
    llm.reply = profile
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    while run_once(app.state.engine):
        pass


def test_a_bio_and_prompts_are_rewritten_for_one_app_from_the_style_profile(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    llm.reply = json.dumps({"bio": "climbs things. cooks ramen.", "prompts": {"A perfect sunday": "ropes, then noodles"}})

    rewrite = client.post(
        "/bios/hinge/rewrite",
        json={"bio": "I like climbing and cooking.", "prompts": {"A perfect sunday": "Climbing and ramen"}},
    )

    assert rewrite.status_code == 200
    assert rewrite.json() == {"bio": "climbs things. cooks ramen.", "prompts": {"A perfect sunday": "ropes, then noodles"}}
    prompt = llm.prompts[-1]
    assert "hinge" in prompt
    assert "Short, lowercase, teasing." in prompt
    assert "I like climbing and cooking." in prompt
    assert "A perfect sunday" in prompt and "Climbing and ramen" in prompt
    assert client.get("/bios/hinge").json() == {"bio": "", "prompts": {}}  # a rewrite is not accepted yet


def test_an_edited_rewrite_can_be_regenerated(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    llm.reply = json.dumps({"bio": "climbs things. cooks ramen.", "prompts": {}})
    first = client.post("/bios/tinder/rewrite", json={"bio": "I like climbing and cooking."}).json()

    llm.reply = json.dumps({"bio": "climbs things, badly. cooks ramen, well.", "prompts": {}})
    edited = {**first, "bio": first["bio"] + " bad at climbing."}
    second = client.post("/bios/tinder/rewrite", json=edited)

    assert second.json()["bio"] == "climbs things, badly. cooks ramen, well."
    assert "climbs things. cooks ramen. bad at climbing." in llm.prompts[-1]


def test_the_accepted_version_is_stored_per_app_and_per_user(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    hinge = {"bio": "climbs things.", "prompts": {"A perfect sunday": "ropes, then noodles"}}

    assert alice.put("/bios/hinge", json=hinge).status_code == 200
    alice.put("/bios/tinder", json={"bio": "first try", "prompts": {}})
    alice.put("/bios/tinder", json={"bio": "ramen > you", "prompts": {}})

    assert alice.get("/bios/hinge").json() == hinge
    assert alice.get("/bios/tinder").json() == {"bio": "ramen > you", "prompts": {}}
    assert bob.get("/bios/hinge").json() == {"bio": "", "prompts": {}}


def test_accepting_a_bio_is_recorded_in_the_audit_log_without_its_text(client):
    client.put("/bios/hinge", json={"bio": "climbs things.", "prompts": {}})

    (entry,) = client.get("/audit-log").json()
    assert (entry["type"], entry["app"], entry["target"]) == ("profile_change", "hinge", "bio")
    assert entry["trigger"] == "copilot: user accepted a bio"


def test_a_rewrite_needs_a_style_profile(client, llm):
    rewrite = client.post("/bios/hinge/rewrite", json={"bio": "I like climbing."})

    assert rewrite.status_code == 409
    assert llm.prompts == []


def test_a_reply_that_is_not_a_bio_is_reported_not_returned(app, client, llm):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    llm.reply = "Sure! Here is your bio."

    assert client.post("/bios/hinge/rewrite", json={"bio": "I like climbing."}).status_code == 502
