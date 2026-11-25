from decimal import Decimal

import pytest
from sqlalchemy import text

from app import llm as claude
from app.jobs import enqueue, handler, run_once


@pytest.fixture(autouse=True)
def one_dollar_calls(monkeypatch):
    # The stub answers as model "stub" with 1 input and 1 output token: each call costs 1 USD.
    monkeypatch.setitem(claude.PRICES, "stub", (Decimal(500_000), Decimal(500_000)))


@pytest.fixture
def user_id(client, app):
    with app.state.engine.connect() as db:
        return db.execute(text("SELECT id FROM users WHERE email = 'user@example.com'")).scalar_one()


@pytest.fixture
def ask(app, user_id):
    """`ask()` makes one Claude call for the test user, as a feature would."""

    def ask(for_user: int = user_id):
        with app.state.engine.begin() as db:
            return claude.call(db, for_user, "test", system="s", prompt="p")

    return ask


def last_month(app):
    """Move every recorded call to the month before this one."""
    with app.state.engine.begin() as db:
        db.execute(text("UPDATE llm_calls SET created_at = date_trunc('month', now()) - interval '1 day'"))


def test_api_returns_this_months_spend_and_the_cap_the_user_set(client, client_for, ask):
    other = client_for("other@example.com")
    assert client.get("/budget").json() == {"spend_usd": 0, "cap_usd": 50, "paused": False}

    assert client.put("/budget", json={"cap_usd": 20}).json()["cap_usd"] == 20
    ask()
    ask()

    assert client.get("/budget").json() == {"spend_usd": 2, "cap_usd": 20, "paused": False}
    assert other.get("/budget").json() == {"spend_usd": 0, "cap_usd": 50, "paused": False}
    assert client.put("/budget", json={"cap_usd": -1}).status_code == 422


def test_spend_counts_only_calls_of_the_current_month(client, app, ask):
    ask()
    last_month(app)
    ask()

    assert client.get("/budget").json()["spend_usd"] == 1


def test_at_the_cap_no_further_model_call_is_made(client, ask, llm):
    client.put("/budget", json={"cap_usd": 2})
    ask()
    ask()

    with pytest.raises(claude.BudgetReached):
        ask()

    assert len(llm.prompts) == 2
    assert client.get("/budget").json() == {"spend_usd": 2, "cap_usd": 2, "paused": True}


def test_a_route_that_needs_the_model_answers_402_at_the_cap(client, app, llm):
    client.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    while run_once(app.state.engine):  # writes the style profile
        pass
    client.put("/budget", json={"cap_usd": 0})

    assert client.post("/bios/hinge/rewrite", json={"bio": "I like climbing."}).status_code == 402


def test_reaching_the_cap_alerts_the_user_once(client, ask, apns):
    client.post("/devices", json={"token": "abc123"})
    client.put("/budget", json={"cap_usd": 2})

    ask()
    assert apns.sent == []
    ask()
    with pytest.raises(claude.BudgetReached):
        ask()

    assert [push["payload"]["aps"]["alert"]["title"] for push in apns.sent] == ["AI budget reached"]


def incoming(client, body: str) -> dict:
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    return client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": body}).json()


def test_jev_checks_are_recorded_under_the_same_budget(client, jev, monkeypatch):
    monkeypatch.setattr("app.jev.PRICE_USD", Decimal("0.25"))

    incoming(client, "hey")  # one sentence, asked about by the five handover checks

    assert len(jev.asked) == 5
    assert client.get("/budget").json()["spend_usd"] == 1.25


def test_at_the_cap_jev_is_not_called_and_its_checks_fail_closed(client, jev):
    client.put("/budget", json={"cap_usd": 0})

    message = incoming(client, "hey")

    assert jev.asked == []
    assert message["handover"] == ["unavailable"]


@pytest.fixture
def swipe_job(client, app, user_id):
    """`swipe_job()` queues an autopilot job for the test user and returns its status once the worker ran it."""
    client.put("/autonomy/swipe", json={"level": "full"})

    @handler("test_budget_swipe", autopilot="swipe")
    def swipe(db, user_id, payload):
        pass

    def swipe_job() -> dict:
        with app.state.engine.begin() as db:
            job_id = enqueue(db, user_id, "test_budget_swipe", {"app": "tinder"})
        run_once(app.state.engine)
        return client.get(f"/jobs/{job_id}").json()

    return swipe_job


def test_autopilot_is_paused_at_the_cap_and_runs_again_when_the_cap_is_raised(client, ask, swipe_job):
    client.put("/budget", json={"cap_usd": 1})
    assert swipe_job()["status"] == "done"

    ask()
    skipped = swipe_job()
    assert skipped["status"] == "skipped"
    assert skipped["last_error"] == "autopilot paused for all apps: AI budget reached"

    client.put("/budget", json={"cap_usd": 5})
    assert swipe_job()["status"] == "done"


def test_a_new_month_lifts_the_budget_pause_but_not_a_pause_set_for_another_reason(client, app, ask, swipe_job):
    client.put("/budget", json={"cap_usd": 1})
    ask()
    client.post("/autopilot/pause", params={"app": "tinder"})

    last_month(app)

    assert client.get("/budget").json()["paused"] is False
    assert "paused by user" in swipe_job()["last_error"]
    client.post("/autopilot/resume", params={"app": "tinder"})
    assert swipe_job()["status"] == "done"
    ask()  # and the model can be called again


def test_the_cost_of_a_call_is_kept_when_the_job_that_made_it_fails(client, app, user_id):
    @handler("test_budget_failing")
    def failing(db, user_id, payload):
        claude.call(db, user_id, "test", system="s", prompt="p")
        raise RuntimeError("after the call")

    with app.state.engine.begin() as db:
        enqueue(db, user_id, "test_budget_failing")
    run_once(app.state.engine)

    assert client.get("/budget").json()["spend_usd"] == 1
