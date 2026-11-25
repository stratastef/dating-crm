"""Paid items (Super Like, Boost, Rose): proposed, then spent only on the user's approval. No live calls."""

import re
from pathlib import Path

import pytest
from sqlalchemy import text

from app.connectors import PAID_ITEMS, PaidItemNeedsApproval, call
from app.paid_items import NotApproved, propose, spend
from app.tinder import TinderConnector
from app.vault import store_token
from tests.test_swipe_autopilot import audit, autopilot, signed_in  # noqa: F401  (fixtures)
from tests.test_swipes import EVE, TOKEN, db, tinder, user_id  # noqa: F401  (fixtures)

SUPER_LIKE = f"POST /like/{EVE}/super"


def paid_items(client) -> list[dict]:
    return [item for item in client.get("/queue").json() if item["kind"] == "paid_item"]


def test_autopilot_proposes_a_super_like_in_the_review_queue_and_spends_nothing(signed_in, tinder, autopilot, llm):
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    llm.replies = ["super like\nShe climbs and wants kids."]  # Eve; Dana is Jev's pass and Fay a plain like

    assert autopilot()["status"] == "done"

    [item] = paid_items(signed_in)
    assert (item["card_name"], item["hot"], item["card_id"]) == ("Eve", False, None)
    assert item["paid_item"] == {
        "id": item["paid_item"]["id"],
        "app": "tinder",
        "item": "super_like",
        "name": "Eve",
        "reason": "She climbs and wants kids.",
        "status": "pending",
    }
    # Autopilot waits: Eve is neither super liked nor liked, and nothing about her is in the audit log.
    assert not any(EVE in call for call in tinder.calls())
    assert [entry[0] for entry in audit(signed_in)] == ["pass", "like"]
    # The next run still waits.
    autopilot()
    assert not any(EVE in call for call in tinder.calls())
    assert all(call.startswith("GET") for call in tinder.calls())  # every paid endpoint is a POST


# Approval: the user's answer in the review queue is the only thing that spends.


@pytest.fixture
def proposed(signed_in, tinder, llm):
    """A Super Like for Eve waits in the queue (proposed by the copilot's screening). Returns the paid item."""
    llm.replies = ["pass\nNothing in common.", "super like\nShe climbs and wants kids."]  # Dana, then Eve
    assert signed_in.post("/swipes/tinder/suggestions").status_code == 200
    [item] = paid_items(signed_in)
    return item["paid_item"]


def answer(client, proposal: dict, verb: str):
    return client.post(f"/paid-items/{proposal['id']}/{verb}")


def test_an_approved_super_like_is_spent_once_and_is_in_the_audit_log(signed_in, tinder, proposed):
    assert SUPER_LIKE not in tinder.calls()

    response = answer(signed_in, proposed, "approve")

    assert response.status_code == 200 and response.json() == {**proposed, "status": "spent"}
    assert tinder.calls().count(SUPER_LIKE) == 1
    [entry] = signed_in.get("/audit-log?type=super_like").json()
    eve = signed_in.get("/people/candidates?q=Eve").json()[0]
    assert (entry["app"], entry["target"], entry["trigger"]) == (
        "tinder",
        f"candidate:{eve['id']}",
        f"paid item: user approved proposal {proposed['id']}",
    )
    # It left the queue, Eve is swiped on, and the approval cannot be used a second time.
    assert paid_items(signed_in) == [] and eve["decision"] == "like"
    assert answer(signed_in, proposed, "approve").status_code == 409
    assert tinder.calls().count(SUPER_LIKE) == 1


def test_a_declined_super_like_is_never_spent_and_autopilot_then_likes_for_free(signed_in, tinder, proposed, autopilot):
    response = answer(signed_in, proposed, "decline")

    assert response.status_code == 200 and response.json()["status"] == "declined"
    assert paid_items(signed_in) == []
    assert answer(signed_in, proposed, "approve").status_code == 409
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    autopilot()
    assert f"GET /like/{EVE}" in tinder.calls()
    assert not any(call.startswith("POST") for call in tinder.calls())
    assert signed_in.get("/audit-log?type=super_like").json() == []


def test_approving_when_the_account_holds_no_super_like_spends_and_logs_nothing(signed_in, tinder, proposed):
    tinder.super_like = "super_like_none_left"

    assert answer(signed_in, proposed, "approve").json()["status"] == "failed"

    assert signed_in.get("/audit-log?type=super_like").json() == []
    assert "Eve" in [candidate["name"] for candidate in signed_in.get("/swipes").json()]  # still waits for a swipe
    assert answer(signed_in, proposed, "approve").status_code == 409  # a failed spend is not tried again


def test_approving_while_tinder_fails_logs_nothing(signed_in, tinder, proposed):
    tinder.status = 500

    assert answer(signed_in, proposed, "approve").json()["status"] == "failed"

    assert signed_in.get("/audit-log?type=super_like").json() == []


def test_a_proposal_leaves_the_queue_when_the_user_swipes_on_the_profile_themselves(signed_in, tinder, proposed):
    eve = signed_in.get("/people/candidates?q=Eve").json()[0]
    assert signed_in.post(f"/swipes/{eve['id']}/decision", json={"decision": "pass"}).status_code == 200

    assert paid_items(signed_in) == []
    assert answer(signed_in, proposed, "approve").status_code == 409
    assert SUPER_LIKE not in tinder.calls()


def test_another_user_can_neither_see_nor_approve_nor_decline_the_proposal(signed_in, client_for, tinder, proposed):
    other = client_for("other@example.com")

    assert paid_items(other) == []
    assert answer(other, proposed, "approve").status_code == 404
    assert answer(other, proposed, "decline").status_code == 404
    assert SUPER_LIKE not in tinder.calls() and paid_items(signed_in) != []


def test_an_approved_boost_is_spent_and_logged(app, signed_in, tinder):
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        assert propose(db, user_id, "tinder", "boost", "Sunday evening is the busiest hour")
        assert propose(db, user_id, "tinder", "boost", "again") is None  # one waits already
    [item] = paid_items(signed_in)
    assert (item["card_name"], item["paid_item"]["item"]) == ("tinder", "boost")

    assert answer(signed_in, item["paid_item"], "approve").json()["status"] == "spent"

    assert tinder.calls() == ["POST /boost"]
    [entry] = signed_in.get("/audit-log?type=boost").json()
    assert (entry["app"], entry["target"]) == ("tinder", "account")


def test_an_item_no_connector_can_spend_is_not_proposed(app, signed_in, tinder, monkeypatch, llm):
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        assert propose(db, user_id, "tinder", "rose", "no such thing on Tinder") is None
        assert propose(db, user_id, "hinge", "rose", "Hinge has no connector yet") is None
    # Switched off by configuration, a Super Like is not proposed either: the profile is a plain like.
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:super_like")
    llm.replies = ["pass\nNothing in common.", "super like\nShe climbs."]  # Dana, then Eve
    signed_in.post("/swipes/tinder/suggestions")

    assert paid_items(signed_in) == []
    assert [c["suggestion"] for c in signed_in.get("/swipes").json() if c["name"] == "Eve"] == ["like"]


# The approval is structural: no other path reaches a connector's paid capability.


@pytest.mark.parametrize("item", sorted(PAID_ITEMS))
def test_call_refuses_every_paid_item_so_no_caller_of_it_can_spend(db, user_id, tinder, item):
    with pytest.raises(PaidItemNeedsApproval):
        call(db, user_id, TinderConnector(), item, EVE)

    assert tinder.requests == []


@pytest.mark.parametrize("status", ["pending", "declined", "spent", "failed"])
def test_spend_refuses_a_proposal_that_is_not_approved(app, signed_in, tinder, proposed, status):
    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        row = db.execute(
            text("UPDATE paid_item_proposals SET status = :status RETURNING *"), {"status": status}
        ).one()
        with pytest.raises(NotApproved):
            spend(db, user_id, row)

    assert SUPER_LIKE not in tinder.calls()


def test_spend_refuses_another_users_approved_proposal_and_a_second_use(app, signed_in, client_for, tinder, proposed):
    client_for("other@example.com")
    with app.state.engine.begin() as db:
        owner, other = db.execute(text("SELECT id FROM users ORDER BY id")).scalars()
        store_token(db, other, "tinder", TOKEN)
        row = db.execute(text("UPDATE paid_item_proposals SET status = 'approved' RETURNING *")).one()
        with pytest.raises(NotApproved):
            spend(db, other, row)
        assert SUPER_LIKE not in tinder.calls()

        assert spend(db, owner, row) == "spent"
        with pytest.raises(NotApproved):
            spend(db, owner, row)  # the same row, still reading `approved` in memory

    assert tinder.calls().count(SUPER_LIKE) == 1


def test_no_module_but_paid_items_can_reach_a_paid_capability():
    """Reads the source. `_run()` is `call()` without the paid-item refusal, and a connector's paid methods
    are reached by name through it: so nothing else may name `_run`, a paid method or `getattr`."""
    sources = {path.name: path.read_text() for path in (Path(__file__).parent.parent / "app").glob("*.py")}

    def naming(pattern: str) -> set[str]:
        return {name for name, source in sources.items() if re.search(pattern, source)}

    assert naming(r"\b_run\b") == {"connectors.py", "paid_items.py"}
    assert naming(r"\.(super_like|rose|boost)\(") == set()
    # modules.py reads only the name `router` off each app module, to register its routes
    assert naming(r"getattr\(") == {"connectors.py", "modules.py"}
    assert sources["paid_items.py"].count("_run(") == 1  # inside `spend()`, after the claim
