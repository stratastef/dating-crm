import pytest
from sqlalchemy import text

from app.jobs import enqueue, handler, run_once


def test_autonomy_defaults_to_copilot_with_swipe_off(client):
    assert client.get("/autonomy").json() == {"chat": "copilot", "profile": "copilot", "swipe": "off"}


def test_user_sets_autonomy_for_one_job(client, client_for):
    other = client_for("other@example.com")

    assert client.put("/autonomy/swipe", json={"level": "guardrails"}).status_code == 200
    client.put("/autonomy/swipe", json={"level": "full"})

    assert client.get("/autonomy").json() == {"chat": "copilot", "profile": "copilot", "swipe": "full"}
    assert other.get("/autonomy").json()["swipe"] == "off"


def test_unknown_job_or_level_is_rejected(client):
    assert client.put("/autonomy/dance", json={"level": "full"}).status_code == 422
    assert client.put("/autonomy/chat", json={"level": "yolo"}).status_code == 422


def test_user_pauses_and_resumes_all_autopilot_or_one_app(client, client_for):
    other = client_for("other@example.com")
    assert client.get("/autopilot/pause").json() == {"all": False, "apps": []}

    client.post("/autopilot/pause", params={"app": "tinder"})
    client.post("/autopilot/pause", params={"app": "tinder"})  # pausing twice is harmless
    assert client.post("/autopilot/pause").json() == {"all": True, "apps": ["tinder"]}
    assert other.get("/autopilot/pause").json() == {"all": False, "apps": []}

    # Resuming all lifts the global pause only: an app paused on its own stays paused.
    assert client.post("/autopilot/resume").json() == {"all": False, "apps": ["tinder"]}
    assert client.post("/autopilot/resume", params={"app": "tinder"}).json() == {"all": False, "apps": []}


@pytest.fixture
def swipe_job(client, app):
    """`swipe_job("tinder")` queues an autopilot swipe job for the test user and returns its id. `ran` lists the apps swiped."""
    ran = []

    @handler("test_swipe", autopilot="swipe")
    def swipe(db, user_id, payload):
        ran.append(payload["app"])

    def swipe_job(app_name: str) -> int:
        with app.state.engine.begin() as db:
            user_id = db.execute(text("SELECT id FROM users WHERE email = 'user@example.com'")).scalar_one()
            return enqueue(db, user_id, "test_swipe", {"app": app_name})

    swipe_job.ran = ran
    return swipe_job


def test_worker_skips_autopilot_jobs_for_a_paused_app_and_records_why(client, app, swipe_job):
    client.put("/autonomy/swipe", json={"level": "full"})
    client.post("/autopilot/pause", params={"app": "tinder"})
    tinder, hinge = swipe_job("tinder"), swipe_job("hinge")

    while run_once(app.state.engine):
        pass

    assert swipe_job.ran == ["hinge"]
    assert client.get(f"/jobs/{hinge}").json()["status"] == "done"
    skipped = client.get(f"/jobs/{tinder}").json()
    assert skipped["status"] == "skipped"
    assert skipped["last_error"] == "autopilot paused for tinder: paused by user"


def test_worker_skips_every_autopilot_job_while_all_apps_are_paused(client, app, swipe_job):
    client.put("/autonomy/swipe", json={"level": "full"})
    client.post("/autopilot/pause")
    paused = swipe_job("hinge")
    ping = client.post("/jobs/ping").json()["id"]

    while run_once(app.state.engine):
        pass

    assert client.get(f"/jobs/{paused}").json()["last_error"] == "autopilot paused for all apps: paused by user"
    assert client.get(f"/jobs/{ping}").json()["status"] == "done"  # not an autopilot job

    client.post("/autopilot/resume")
    swipe_job("hinge")
    run_once(app.state.engine)
    assert swipe_job.ran == ["hinge"]


def test_worker_skips_an_autopilot_job_whose_autonomy_is_off(client, app, swipe_job):
    job_id = swipe_job("tinder")

    run_once(app.state.engine)

    assert swipe_job.ran == []
    assert client.get(f"/jobs/{job_id}").json()["last_error"] == "swipe autonomy is off"
