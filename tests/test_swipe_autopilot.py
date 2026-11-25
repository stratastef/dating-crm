"""Swipe autopilot on Tinder: the worker's `swipe_autopilot` job, against the stubs. No live calls."""

import pytest
from sqlalchemy import text

from app.jev import JevUnavailable
from app.jobs import enqueue, enqueue_recurring, run_once
from app.vault import store_token
from tests.test_swipes import DANA, EVE, FAY, TOKEN, tinder  # noqa: F401  (fixture)

RECS = "GET /v2/recs/core"


@pytest.fixture
def signed_in(app, client, tinder):
    """The user's client, with their Tinder token stored. Not through the API: that would queue a match sync."""
    with app.state.engine.begin() as db:
        store_token(db, db.execute(text("SELECT id FROM users")).scalar_one(), "tinder", TOKEN)
    return client


@pytest.fixture
def autopilot(app, signed_in, jev, llm):
    """`autopilot()` queues one `swipe_autopilot` job for the user, runs it and returns the job.

    Dana's bio shows the user's dealbreaker; the cheap model likes everyone else.
    """
    signed_in.put("/preferences", json={"dealbreakers": ["smokes"]})
    jev.yes["dealbreaker"] = ["smoke"]
    llm.reply = "like\nShe climbs."

    def autopilot() -> dict:
        with app.state.engine.begin() as db:
            job_id = enqueue(db, db.execute(text("SELECT id FROM users")).scalar_one(), "swipe_autopilot")
        while run_once(app.state.engine):
            pass
        return signed_in.get(f"/jobs/{job_id}").json()

    return autopilot


def audit(client) -> list[tuple[str, str, str]]:
    return [(entry["type"], entry["app"], entry["trigger"]) for entry in reversed(client.get("/audit-log").json())]


def swipes(tinder) -> list[str]:
    return [call for call in tinder.calls() if call != RECS]


def test_with_swipe_autonomy_on_the_worker_likes_and_passes_alone_and_logs_each_with_its_trigger(
    signed_in, tinder, autopilot
):
    signed_in.put("/autonomy/swipe", json={"level": "guardrails"})

    assert autopilot()["status"] == "done"

    assert tinder.calls() == [RECS, f"GET /pass/{DANA}", f"GET /like/{EVE}", f"GET /like/{FAY}"]
    assert audit(signed_in) == [
        ("pass", "tinder", "swipe autopilot: jev dealbreaker"),
        ("like", "tinder", "swipe autopilot: model pre-screen"),
        ("like", "tinder", "swipe autopilot: model pre-screen"),
    ]
    assert signed_in.get("/swipes").json() == []  # nothing is left for the user to confirm


@pytest.mark.parametrize("level", [None, "off", "copilot"])
def test_nothing_is_swiped_unattended_until_the_user_turns_swipe_autonomy_on(signed_in, tinder, autopilot, level):
    if level:
        signed_in.put("/autonomy/swipe", json={"level": level})

    job = autopilot()

    assert (job["status"], job["last_error"]) == ("skipped", f"swipe autonomy is {level or 'off'}")
    assert tinder.requests == [] and audit(signed_in) == []


def test_the_recurring_run_is_queued_for_every_user_and_skipped_while_swipe_autonomy_is_off(app, signed_in, tinder):
    enqueue_recurring(app.state.engine)

    with app.state.engine.begin() as db:
        db.execute(text("DELETE FROM jobs WHERE kind <> 'swipe_autopilot'"))  # the other recurring jobs
    assert run_once(app.state.engine) and not run_once(app.state.engine)
    with app.state.engine.begin() as db:
        assert db.execute(text("SELECT status FROM jobs")).scalars().all() == ["skipped"]
    assert tinder.requests == []


def test_the_kill_switch_stops_swipe_autopilot(signed_in, tinder, autopilot):
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    signed_in.post("/autopilot/pause")

    assert autopilot()["last_error"] == "autopilot paused for all apps: paused by user"
    assert tinder.requests == []

    signed_in.post("/autopilot/resume")
    signed_in.post("/autopilot/pause", params={"app": "tinder"})  # the kill switch for one app

    assert autopilot()["status"] == "done"
    assert tinder.requests == [] and audit(signed_in) == []


def test_a_ban_signal_pauses_the_app_and_swipe_autopilot_stays_stopped(app, signed_in, tinder, autopilot):
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    tinder.status = 403
    autopilot()
    assert signed_in.get("/autopilot/pause").json() == {"all": False, "apps": ["tinder"]}
    tinder.status = 200
    with app.state.engine.begin() as db:
        db.execute(text("DELETE FROM connector_alerts"))  # even with the copilot-only fallback gone, the pause holds

    autopilot()

    assert tinder.calls() == [RECS] and audit(signed_in) == []


def test_the_ai_budget_cap_stops_swipe_autopilot(signed_in, tinder, autopilot, llm):
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    signed_in.put("/budget", json={"cap_usd": 0})

    assert autopilot()["last_error"] == "autopilot paused for all apps: AI budget reached"
    assert tinder.requests == [] and llm.prompts == []


def test_swipe_autopilot_sends_plain_likes_and_passes_and_never_spends_a_paid_item(signed_in, tinder, autopilot):
    signed_in.put("/autonomy/swipe", json={"level": "full"})

    autopilot()

    assert len(swipes(tinder)) == 3
    assert all(call.startswith(("GET /like/", "GET /pass/")) for call in swipes(tinder))
    assert not any("super" in str(request.url) or request.content for request in tinder.requests)


def test_swipes_are_bounded_per_run_and_per_day_by_a_user_setting_with_a_low_default(signed_in, tinder, autopilot):
    assert signed_in.get("/swipes/limits").json() == {"swipes_per_run": 5, "swipes_per_day": 20}
    assert signed_in.put("/swipes/limits", json={"swipes_per_run": 0, "swipes_per_day": 20}).status_code == 422
    assert signed_in.put("/swipes/limits", json={"swipes_per_run": 5, "swipes_per_day": 1000}).status_code == 422
    limits = {"swipes_per_run": 1, "swipes_per_day": 2}
    assert signed_in.put("/swipes/limits", json=limits).json() == limits
    signed_in.put("/autonomy/swipe", json={"level": "full"})

    autopilot()
    assert swipes(tinder) == [f"GET /pass/{DANA}"]  # one per run

    autopilot()
    autopilot()
    assert swipes(tinder) == [f"GET /pass/{DANA}", f"GET /like/{EVE}"]  # two per day
    assert [candidate["name"] for candidate in signed_in.get("/swipes").json()] == ["Fay"]


def test_without_a_dealbreaker_check_no_profile_is_swiped_unattended(signed_in, tinder, autopilot, monkeypatch):
    signed_in.put("/autonomy/swipe", json={"level": "full"})

    def jev_is_down(sentence, check, subject=""):
        raise JevUnavailable("down")

    monkeypatch.setattr("app.jev.ask", jev_is_down)

    assert autopilot()["status"] == "done"

    # Fay's bio is empty, so there was nothing to ask Jev about her: she is the only one swiped.
    assert swipes(tinder) == [f"GET /like/{FAY}"]
    # The cheap model still suggested for the others, so the user can decide each one.
    assert [candidate["name"] for candidate in signed_in.get("/swipes").json()] == ["Dana", "Eve"]


def test_a_dealbreaker_added_after_screening_turns_the_stored_like_into_a_pass(signed_in, tinder, autopilot, jev):
    signed_in.post("/swipes/tinder/suggestions")  # copilot screened Eve as a like
    signed_in.put("/preferences", json={"dealbreakers": ["smokes", "climbs"]})
    jev.yes["dealbreaker"] = ["smoke", "climber"]
    signed_in.put("/autonomy/swipe", json={"level": "full"})

    autopilot()

    assert f"GET /pass/{EVE}" in tinder.calls()


def test_a_person_held_only_as_a_swipe_candidate_is_found_and_purged_with_the_audit_entries_about_them(
    signed_in, tinder, autopilot, client_for
):
    signed_in.put("/autonomy/swipe", json={"level": "full"})
    autopilot()
    other = client_for("other@example.com")

    def found(client, q):
        return client.get("/people/candidates", params={"q": q}).json()

    (eve,) = found(signed_in, "EVE")
    assert (eve["name"], eve["app"], eve["decision"]) == ("Eve", "tinder", "like")
    assert found(signed_in, EVE) == [eve]  # by the app's profile ID too
    assert found(other, "eve") == []
    body = {"candidate_ids": [eve["id"]], "confirm": "purge"}
    assert other.post("/people/purge", json=body).status_code == 404

    assert signed_in.post("/people/purge", json=body).json() == {"purged": 1}

    assert found(signed_in, "eve") == [] and len(found(signed_in, "a")) == 2  # Dana and Fay stay
    assert [(entry["type"], entry["target"], entry["trigger"]) for entry in signed_in.get("/audit-log").json()] == [
        ("purge", f"candidate:{eve['id']}", "deletion request"),
        ("like", f"candidate:{eve['id'] + 1}", "swipe autopilot: model pre-screen"),
        ("pass", f"candidate:{eve['id'] - 1}", "swipe autopilot: jev dealbreaker"),
    ]
    assert signed_in.post("/people/purge", json={"confirm": "purge"}).status_code == 422  # nobody named
