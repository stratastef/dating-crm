"""Job queue in Postgres. The API enqueues with `enqueue()`; the worker runs handlers registered with `@handler`."""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy import Connection, Engine, text

from app.autopilot import Job, autopilot_block

log = logging.getLogger("jobs")

MAX_ATTEMPTS = 5
RETRY_DELAY = timedelta(seconds=30)  # doubles after each failed attempt

# handler(db, user_id, payload). `db` is the job's own transaction: its writes commit only if the handler returns.
Handler = Callable[[Connection, int, dict], None]
_handlers: dict[str, Handler] = {}
_autopilot_jobs: dict[str, Job] = {}  # job kind -> the autonomy job it acts for


_recurring: dict[str, timedelta] = {}  # job kind -> how often it runs for each user


def handler(
    kind: str, autopilot: Job | None = None, every: timedelta | None = None
) -> Callable[[Handler], Handler]:
    """Register the function that runs jobs of this kind: `@handler("sync_matches")`.

    `autopilot="chat"` marks an autopilot job: the worker skips it unless `autopilot_block()` allows it for
    the app in `payload["app"]`.

    With `every=`, the job is recurring: `enqueue_recurring()` queues it for each user once per interval.
    """

    def register(function: Handler) -> Handler:
        _handlers[kind] = function
        if autopilot:
            _autopilot_jobs[kind] = autopilot
        if every:
            _recurring[kind] = every
        return function

    return register


def enqueue_recurring(engine: Engine, now: datetime | None = None) -> None:
    """Queue each recurring job for every user who has none queued and none scheduled within the last interval."""
    with engine.begin() as db:
        now = now or db.execute(text("SELECT now()")).scalar_one()
        assert now
        for kind, every in _recurring.items():
            # shortcut: two workers polling at once can queue the same job twice, and one row is kept per run;
            # add a unique index on queued (user_id, kind) and prune `done` rows if either starts to matter.
            db.execute(
                text(
                    "INSERT INTO jobs (user_id, kind, payload, run_at) SELECT id, :kind, '{}', :now FROM users u"
                    " WHERE NOT EXISTS (SELECT 1 FROM jobs j WHERE j.user_id = u.id AND j.kind = :kind"
                    " AND (j.status = 'queued' OR j.run_at > :since))"
                ),
                {"kind": kind, "now": now, "since": now - every},
            )


def enqueue(
    db: Connection, user_id: int, kind: str, payload: dict | None = None, run_at: datetime | None = None
) -> int:
    """Queue a job in the caller's transaction and return its id. It runs at `run_at`, or as soon as possible."""
    return db.execute(
        text(
            "INSERT INTO jobs (user_id, kind, payload, run_at)"
            " VALUES (:user_id, :kind, :payload, coalesce(CAST(:run_at AS timestamptz), now())) RETURNING id"
        ),
        {"user_id": user_id, "kind": kind, "payload": json.dumps(payload or {}), "run_at": run_at},
    ).scalar_one()


def run_once(engine: Engine, now: datetime | None = None) -> bool:
    """Claim and run one due job. Returns False when no job is due. `now` defaults to the database clock."""
    with engine.begin() as db:
        now = now or db.execute(text("SELECT now()")).scalar_one()
        # The row lock is the claim: other workers skip this job, and a crashed worker releases it.
        # shortcut: the transaction stays open while the handler runs, move to a `running` status with a lease if handlers get slow.
        job = db.execute(
            text(
                "SELECT id, user_id, kind, payload, attempts FROM jobs WHERE status = 'queued' AND run_at <= :now"
                " ORDER BY run_at, id LIMIT 1 FOR UPDATE SKIP LOCKED"
            ),
            {"now": now},
        ).one_or_none()
        if job is None:
            return False
        if job.kind in _autopilot_jobs:
            block = autopilot_block(db, job.user_id, job.payload.get("app"), _autopilot_jobs[job.kind])
            if block:
                # Skipped jobs are not retried: whatever resumes autopilot queues fresh work.
                db.execute(
                    text("UPDATE jobs SET status = 'skipped', last_error = :why WHERE id = :id"),
                    {"id": job.id, "why": block},
                )
                return True
        try:
            # The savepoint undoes a failed handler's writes but keeps the claim.
            with db.begin_nested():
                _handlers[job.kind](db, job.user_id, job.payload)
        except Exception as error:  # an unknown kind fails the same way
            log.exception("job %s (%s) failed", job.id, job.kind)
            attempts = job.attempts + 1
            db.execute(
                text(
                    "UPDATE jobs SET attempts = :attempts, status = :status, run_at = :run_at, last_error = :error"
                    " WHERE id = :id"
                ),
                {
                    "id": job.id,
                    "attempts": attempts,
                    "status": "failed" if attempts >= MAX_ATTEMPTS else "queued",
                    "run_at": now + RETRY_DELAY * 2 ** (attempts - 1),  # 30s, 1m, 2m, 4m
                    "error": repr(error),
                },
            )
        else:
            db.execute(text("UPDATE jobs SET status = 'done', attempts = attempts + 1 WHERE id = :id"), {"id": job.id})
        return True


@handler("ping")
def _ping(db: Connection, user_id: int, payload: dict) -> None:
    """Does nothing. `POST /jobs/ping` queues it to check that the worker is alive."""
