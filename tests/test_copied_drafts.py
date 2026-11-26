"""Copy (ADR 0003): a copied draft stays in view until the user's message shows up in the chat.

Drafts, messages and screenshots go in through the API; `GET /queue` and `GET /pipeline` are read back.
"""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.tinder import TinderConnector
from tests.test_autopilot import alembic
from tests.test_drafts import write_profile
from tests.test_screenshots import share
from tests.test_send import CLEO, TOKEN, draft, tinder, user_id, work  # noqa: F401  (fixtures)


def unlinked_draft(app, client, llm) -> dict:
    """A pending draft on a Hinge card typed in by hand: no connector, no match ID."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    return client.post(f"/cards/{card_id}/drafts").json()


def waiting(client) -> list[tuple[str, int]]:
    """The review queue as (kind, draft id)."""
    return [(item["kind"], item["draft"]["id"]) for item in client.get("/queue").json() if item["draft"]]


def test_copy_moves_a_pending_draft_to_copied_on_a_card_the_app_can_send_to(app, client, draft, tinder):  # noqa: F811
    copied = client.post(f"/drafts/{draft['id']}/copy")

    assert copied.status_code == 200
    assert copied.json()["status"] == "copied"
    work(app)
    assert tinder.sent == []  # copying sends nothing
    assert waiting(client) == [("copied_draft", draft["id"])]


def test_copy_moves_a_pending_draft_to_copied_on_a_card_the_app_cannot_send_to(app, client, llm):
    pending = unlinked_draft(app, client, llm)

    copied = client.post(f"/drafts/{pending['id']}/copy")

    assert copied.status_code == 200
    assert copied.json()["status"] == "copied"
    assert waiting(client) == [("copied_draft", pending["id"])]


def test_copy_moves_a_failed_draft_to_copied(app, client, draft, tinder):  # noqa: F811
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)

    copied = client.post(f"/drafts/{draft['id']}/copy")

    assert copied.status_code == 200
    assert copied.json()["status"] == "copied"
    assert waiting(client) == [("copied_draft", draft["id"])]


def test_only_the_users_own_pending_or_failed_draft_can_be_copied(app, client, client_for, draft, tinder):  # noqa: F811
    assert client_for("bob@example.com").post(f"/drafts/{draft['id']}/copy").status_code == 404
    client.post(f"/drafts/{draft['id']}/send")
    work(app)

    refused = client.post(f"/drafts/{draft['id']}/copy")

    assert refused.status_code == 409
    assert refused.json()["detail"] == "the draft is sent"


def sendable(client) -> dict[str, bool]:
    """Each draft in the review queue: can the app send it now, by card name."""
    return {item["card_name"]: item["draft"]["sendable"] for item in client.get("/queue").json()}


def test_a_draft_on_a_linked_card_of_a_working_connector_is_sendable(client, draft):  # noqa: F811
    assert draft["sendable"] is True
    assert sendable(client) == {"Cleo": True}


def test_a_draft_on_an_unlinked_card_a_broken_connector_or_an_app_without_one_is_not_sendable(
    app, client, llm, draft, tinder  # noqa: F811
):
    unlinked = client.post("/cards", json={"app": "tinder", "name": "Typed in by hand"}).json()["id"]
    client.post(f"/cards/{unlinked}/drafts")
    unlinked_draft(app, client, llm)  # Sam on Hinge
    assert sendable(client) == {"Cleo": True, "Typed in by hand": False, "Sam": False}

    tinder.status = 401  # Tinder rejects the session: the connector is broken
    client.post(f"/drafts/{draft['id']}/send")
    work(app)
    client.post(f"/cards/{draft['card_id']}/drafts")

    assert sendable(client) == {"Cleo": False, "Typed in by hand": False, "Sam": False}


def test_autopilot_writes_no_reply_over_a_copied_draft(app, client, draft, tinder):  # noqa: F811
    """The user is about to paste the copied text: a reply from autopilot would cross it."""
    client.post(f"/drafts/{draft['id']}/copy")
    client.put("/autonomy/chat", json={"level": "autopilot"})

    client.post(f"/cards/{draft['card_id']}/messages", json={"sender": "them", "body": "??"})
    work(app)

    assert tinder.sent == []
    assert waiting(client) == [("copied_draft", draft["id"])]


def test_v1_drafts_left_approved_and_never_sent_are_copied_and_a_send_still_queued_goes_out(
    app, client, draft, tinder  # noqa: F811
):
    stuck = draft["id"]  # v1's Approve on a card it could not send to
    queued = client.post(f"/cards/{draft['card_id']}/drafts").json()["id"]
    client.post(f"/drafts/{queued}/send")  # its send job waits for the worker
    alembic("downgrade", "t56_copied_drafts-1")
    try:
        with app.state.engine.begin() as db:
            db.execute(text("UPDATE drafts SET status = 'approved' WHERE id = :id"), {"id": stuck})
    finally:
        alembic("upgrade", "head")

    assert waiting(client) == [("copied_draft", stuck)]
    work(app)
    assert len(tinder.sent) == 1


def reason(client, card_id: int) -> str | None:
    return client.get(f"/cards/{card_id}").json()["reason"]


def test_dismiss_clears_a_copied_draft(app, client, draft):  # noqa: F811
    client.post(f"/drafts/{draft['id']}/copy")
    assert reason(client, draft["card_id"]) == "copied_draft"

    cleared = client.post(f"/drafts/{draft['id']}/dismiss")

    assert cleared.status_code == 200
    assert cleared.json()["status"] == "dismissed"
    assert waiting(client) == []
    assert reason(client, draft["card_id"]) != "copied_draft"


def test_dismiss_clears_a_failed_draft(app, client, draft, tinder):  # noqa: F811
    tinder.status = 500
    client.post(f"/drafts/{draft['id']}/send")
    work(app)
    assert reason(client, draft["card_id"]) == "failed_send"

    cleared = client.post(f"/drafts/{draft['id']}/dismiss")

    assert cleared.status_code == 200
    assert cleared.json()["status"] == "dismissed"
    assert reason(client, draft["card_id"]) != "failed_send"


# A copied draft is sent once the user's own message shows up on its card, however it is recorded.

ME, CLEO_PERSON = CLEO[:24], CLEO[24:]


def by_hand(app, client, llm, monkeypatch, card_id: int, sent_at: datetime) -> None:
    message = {"sender": "me", "body": "both. badly.", "sent_at": sent_at.isoformat()}
    assert client.post(f"/cards/{card_id}/messages", json=message).status_code == 201


def by_screenshot(app, client, llm, monkeypatch, card_id: int, sent_at: datetime) -> None:
    """A screenshot's messages are stamped when it is imported: `sent_at` is ignored."""
    read = {
        "app": "tinder",
        "name": "Cleo",
        "messages": [
            {"sender": "them", "body": "do you climb indoors or outdoors"},
            {"sender": "me", "body": "both. badly."},
        ],
    }
    assert share(client, llm, read).status_code == 201


def by_sync(app, client, llm, monkeypatch, card_id: int, sent_at: datetime) -> None:
    """Tinder serves Cleo's chat, ending with the user's message sent at `sent_at`."""
    stamp = sent_at.isoformat().replace("+00:00", "Z")
    mine = {
        "_id": "64c000000000000000000fff",
        "match_id": CLEO,
        "sent_date": stamp,
        "message": "both. badly.",
        "to": CLEO_PERSON,
        "from": ME,
        "created_date": stamp,
        "timestamp": 0,
    }
    match = {"_id": CLEO, "person": {"_id": CLEO_PERSON, "name": "Cleo"}, "messages": [mine]}

    def serve(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/matches":
            listed = [match] if request.url.params["message"] == "1" else []
            return httpx.Response(200, json={"data": {"matches": listed}})
        return httpx.Response(200, json={"data": {"messages": [mine]}})

    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(serve))
    client.put("/connectors/tinder/token", json={"token": TOKEN})  # syncs now
    work(app)


@pytest.mark.parametrize("record", [by_hand, by_screenshot, by_sync])
def test_a_copied_draft_is_sent_once_a_newer_message_from_the_user_is_recorded(
    app, client, llm, draft, monkeypatch, record  # noqa: F811
):
    client.post(f"/drafts/{draft['id']}/copy")

    record(app, client, llm, monkeypatch, draft["card_id"], sent_at=datetime.now(UTC))

    assert ("copied_draft", draft["id"]) not in waiting(client)
    assert client.post(f"/drafts/{draft['id']}/dismiss").json()["detail"] == "the draft is sent"


@pytest.mark.parametrize("record", [by_hand, by_sync])
def test_a_message_from_the_user_older_than_the_copy_leaves_the_copied_draft_waiting(
    app, client, llm, draft, monkeypatch, record  # noqa: F811
):
    client.post(f"/drafts/{draft['id']}/copy")

    record(app, client, llm, monkeypatch, draft["card_id"], sent_at=datetime.now(UTC) - timedelta(minutes=5))

    assert waiting(client) == [("copied_draft", draft["id"])]
