"""Discreet pushes and Blur photos: the privacy settings under You."""

from tests.test_drafts import drafted, write_profile
from tests.test_review import card_with_reply

GENERIC = "Someone replied. A draft is ready."


def alerts(apns) -> list[tuple[str, str, int]]:
    return [
        (push["payload"]["aps"]["alert"]["title"], push["payload"]["aps"]["alert"]["body"], push["payload"]["card_id"])
        for push in apns.sent
    ]


def test_push_name_previews_and_blur_photos_are_off_by_default(client):
    settings = client.get("/settings").json()
    assert settings["push_name_previews"] is False
    assert settings["blur_photos"] is False

    changed = client.patch("/settings", json={"push_name_previews": True, "blur_photos": True}).json()

    assert (changed["push_name_previews"], changed["blur_photos"]) == (True, True)
    assert client.get("/settings").json()["blur_photos"] is True


def test_a_hot_lead_push_names_nobody_unless_name_previews_are_on(app, client, llm, apns):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post("/devices", json={"token": "abc123"})
    ada = card_with_reply(client, "Ada", minutes_ago=5)
    kim = card_with_reply(client, "Kim", minutes_ago=5)
    llm.reply = drafted("see you saturday")

    client.post(f"/cards/{ada}/drafts")
    client.patch("/settings", json={"push_name_previews": True})
    client.post(f"/cards/{kim}/drafts")

    [discreet, named] = alerts(apns)
    assert discreet == ("Hot lead", GENERIC, ada)  # the card ID still opens the card
    assert "Kim" in named[1]
    assert named[2] == kim


def test_a_handover_push_names_nobody_and_quotes_nothing_unless_name_previews_are_on(client, jev, llm, apns):
    jev.yes["logistics"] = ["saturday"]
    client.post("/devices", json={"token": "abc123"})
    card_id = client.post("/cards", json={"app": "hinge", "name": "Ada"}).json()["id"]
    llm.reply = "saturday works\nhow about sunday instead"

    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "Saturday at 8?"})

    assert alerts(apns) == [("Hot lead", GENERIC, card_id)]
