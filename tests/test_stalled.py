from datetime import UTC, datetime, timedelta

from app.jobs import enqueue_recurring, run_once


def days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def new_card(client, stage: str = "chatting", last_message_days_ago: int | None = None, sender: str = "me") -> int:
    card_id = client.post("/cards", json={"app": "tinder", "name": "Sam", "stage": stage}).json()["id"]
    if last_message_days_ago is not None:
        message = {"sender": sender, "body": "hey", "sent_at": days_ago(last_message_days_ago)}
        assert client.post(f"/cards/{card_id}/messages", json=message).status_code == 201
    return card_id


def run_scheduled_jobs(app) -> None:
    enqueue_recurring(app.state.engine)
    while run_once(app.state.engine):
        pass


def test_silent_days_default_to_three_and_the_user_can_change_them(client):
    assert client.get("/settings").json() == {"stalled_after_days": 3}

    assert client.patch("/settings", json={"stalled_after_days": 5}).status_code == 200

    assert client.get("/settings").json() == {"stalled_after_days": 5}
    assert client.patch("/settings", json={"stalled_after_days": 0}).status_code == 422


def test_scheduled_job_marks_a_card_stalled_after_three_silent_days(client, app):
    silent = {stage: new_card(client, stage, last_message_days_ago=4) for stage in ("chatting", "number_swapped", "date_set")}
    active = new_card(client, "chatting", last_message_days_ago=2)
    other_stage = new_card(client, "matched", last_message_days_ago=4)

    run_scheduled_jobs(app)

    for stage, card_id in silent.items():
        card = client.get(f"/cards/{card_id}").json()
        assert card["stalled"] is True
        assert card["suggested_actions"] == ["revive", "archive"]
        assert card["stage"] == stage  # Stalled is a flag, not a stage
    for card_id in (active, other_stage):
        card = client.get(f"/cards/{card_id}").json()
        assert card["stalled"] is False
        assert card["suggested_actions"] == []


def test_a_new_reply_clears_the_stalled_state(client, app):
    card_id = new_card(client, last_message_days_ago=4)
    run_scheduled_jobs(app)
    assert client.get(f"/cards/{card_id}").json()["stalled"] is True

    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "still up for it?"})
    assert client.get(f"/cards/{card_id}").json()["stalled"] is True  # my own message is not a reply

    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "yes!"})
    card = client.get(f"/cards/{card_id}").json()
    assert card["stalled"] is False
    assert card["suggested_actions"] == []


def test_archiving_a_stalled_card_ends_the_stalled_state(client, app):
    card_id = new_card(client, last_message_days_ago=4)
    run_scheduled_jobs(app)
    assert "archive" in client.get(f"/cards/{card_id}").json()["suggested_actions"]

    archived = client.patch(f"/cards/{card_id}", json={"stage": "archived"}).json()

    assert archived["stage"] == "archived"
    assert archived["stalled"] is False
    assert archived["suggested_actions"] == []


def test_the_job_uses_each_users_own_silent_days(client_for, app):
    patient = client_for("patient@example.com")
    default = client_for("default@example.com")
    patient.patch("/settings", json={"stalled_after_days": 7})
    patient_card = new_card(patient, last_message_days_ago=4)
    default_card = new_card(default, last_message_days_ago=4)

    run_scheduled_jobs(app)

    assert patient.get(f"/cards/{patient_card}").json()["stalled"] is False
    assert default.get(f"/cards/{default_card}").json()["stalled"] is True


def test_the_recurring_job_is_queued_once_per_user_per_hour(client, app):
    # sender "them": a "me" message would also queue a voice_profile job and hide the count below
    card_id = new_card(client, last_message_days_ago=4, sender="them")
    engine = app.state.engine
    now = datetime.now(UTC)

    enqueue_recurring(engine, now=now)
    enqueue_recurring(engine, now=now)  # a second poll must not queue it twice
    assert run_once(engine, now=now) is True
    assert run_once(engine, now=now) is False
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "old one", "sent_at": days_ago(5)})
    assert client.get(f"/cards/{card_id}").json()["stalled"] is False

    enqueue_recurring(engine, now=now + timedelta(minutes=30))
    assert run_once(engine, now=now + timedelta(minutes=30)) is False  # not yet due again

    enqueue_recurring(engine, now=now + timedelta(hours=1, minutes=1))
    assert run_once(engine, now=now + timedelta(hours=1, minutes=1)) is True
    assert client.get(f"/cards/{card_id}").json()["stalled"] is True
