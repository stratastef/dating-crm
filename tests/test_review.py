from datetime import datetime, timedelta, timezone

from tests.test_drafts import write_profile


def card_with_reply(client, name: str, minutes_ago: int) -> int:
    """A card whose match replied that many minutes ago."""
    card_id = client.post("/cards", json={"app": "hinge", "name": name}).json()["id"]
    sent_at = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
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
    assert queue.json() == [
        {"kind": "draft", "hot": True, "card_id": hot, "card_name": "Ada", "draft": hot_draft},
        {"kind": "draft", "hot": False, "card_id": cold, "card_name": "Kim", "draft": cold_draft},
    ]
    assert bob.get("/queue").json() == []


def test_an_approved_draft_leaves_the_queue_and_is_handed_on_with_the_users_edit(app, client, llm, monkeypatch):
    handed_on = []
    monkeypatch.setattr("app.review.hand_on_approved_draft", lambda db, user_id, draft: handed_on.append(draft))
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = card_with_reply(client, "Kim", minutes_ago=90)
    draft_id = client.post(f"/cards/{card_id}/drafts").json()["id"]
    client.patch(f"/drafts/{draft_id}", json={"edited": "saturday it is"})

    approved = client.post(f"/drafts/{draft_id}/approve")

    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert client.get("/queue").json() == []
    assert [(draft.id, draft.edited) for draft in handed_on] == [(draft_id, "saturday it is")]
    assert client.post(f"/drafts/{draft_id}/approve").status_code == 409  # already decided
    assert len(handed_on) == 1


def test_a_dismissed_draft_leaves_the_queue_and_is_not_handed_on(app, client_for, llm, monkeypatch):
    handed_on = []
    monkeypatch.setattr("app.review.hand_on_approved_draft", lambda db, user_id, draft: handed_on.append(draft))
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    write_profile(app, alice, llm, "Short, lowercase, teasing.")
    card_id = card_with_reply(alice, "Kim", minutes_ago=90)
    draft_id = alice.post(f"/cards/{card_id}/drafts").json()["id"]

    assert bob.post(f"/drafts/{draft_id}/dismiss").status_code == 404
    assert bob.post(f"/drafts/{draft_id}/approve").status_code == 404
    dismissed = alice.post(f"/drafts/{draft_id}/dismiss")

    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert alice.get("/queue").json() == []
    assert handed_on == []
