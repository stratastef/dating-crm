import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.jobs import enqueue, handler, run_once


@pytest.fixture
def queue(client, app):
    """`queue(kind, **kwargs)` enqueues a job for the test user and returns its id."""

    def queue(kind: str, **kwargs) -> int:
        with app.state.engine.begin() as db:
            user_id = db.execute(text("SELECT id FROM users")).scalar_one()
            return enqueue(db, user_id, kind, **kwargs)

    return queue


def test_job_enqueued_through_the_api_is_completed_by_the_worker(client, app):
    job_id = client.post("/jobs/ping").json()["id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"

    assert run_once(app.state.engine) is True

    assert client.get(f"/jobs/{job_id}").json()["status"] == "done"
    assert run_once(app.state.engine) is False


def test_job_scheduled_for_later_runs_only_once_it_is_due(app, queue):
    payloads = []
    handler("test_later")(lambda db, user_id, payload: payloads.append(payload))
    due = datetime.now(UTC) + timedelta(hours=1)
    queue("test_later", payload={"n": 1}, run_at=due)

    assert run_once(app.state.engine) is False
    assert payloads == []

    assert run_once(app.state.engine, now=due) is True
    assert payloads == [{"n": 1}]


def test_failing_job_retries_with_backoff_and_ends_failed(client, app, queue):
    calls = []

    @handler("test_boom")
    def boom(db, user_id, payload):
        calls.append(1)
        raise RuntimeError("boom")

    job_id = queue("test_boom")
    later = datetime.now(UTC)

    assert run_once(app.state.engine) is True
    assert client.get(f"/jobs/{job_id}").json() == {"id": job_id, "kind": "test_boom", "status": "queued", "attempts": 1}
    assert run_once(app.state.engine) is False  # backing off

    while run_once(app.state.engine, now=(later := later + timedelta(days=1))):
        pass

    assert len(calls) == 5
    assert client.get(f"/jobs/{job_id}").json()["status"] == "failed"


def test_concurrent_workers_do_not_run_the_same_job_twice(app, queue):
    started, release, calls = threading.Event(), threading.Event(), []

    @handler("test_slow")
    def slow(db, user_id, payload):
        calls.append(1)
        started.set()
        release.wait(timeout=5)

    queue("test_slow")
    first_worker = threading.Thread(target=run_once, args=(app.state.engine,))
    first_worker.start()
    assert started.wait(timeout=5)

    assert run_once(app.state.engine) is False  # the only job is claimed

    release.set()
    first_worker.join()
    assert len(calls) == 1
    assert run_once(app.state.engine) is False
