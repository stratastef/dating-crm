# Background jobs

Jobs are rows in the `jobs` table. The API enqueues them and only the worker runs them. Both functions are in `app/jobs.py`.

Enqueue inside the request transaction. The job is queued only if the request commits. `run_at` is optional and schedules the job for later:

```python
job_id = enqueue(db, user.id, "sync_matches", {"app": "tinder"}, run_at=tomorrow)
```

Register one handler per kind. The worker imports every module in `app/` (see `app/modules.py`), so a handler needs no registration elsewhere:

```python
@handler("sync_matches")
def sync_matches(db: Connection, user_id: int, payload: dict) -> None: ...
```

`db` is the job's own transaction. If the handler raises, its writes are rolled back and the job is retried after 30s, 1m, 2m and 4m. After 5 attempts its status is `failed` and `last_error` holds the exception. Workers claim jobs with `FOR UPDATE SKIP LOCKED`, so several workers can run. A worker that crashes mid-job releases it, so make handlers safe to run twice.

A recurring job is a handler with `every=`. The worker calls `enqueue_recurring()` on each poll, which queues the job for every user who has none queued and none scheduled within the last interval. Users created later are picked up on the next poll.

```python
@handler("mark_stalled", every=timedelta(hours=1))
def mark_stalled(db: Connection, user_id: int, payload: dict) -> None: ...
```

In a test, call `enqueue_recurring(app.state.engine)` to queue the recurring jobs, and `run_once(app.state.engine)` to run the next due job; pass `now=` to move the clock. `POST /jobs/ping` queues a no-op job and `GET /jobs/{id}` returns its `status` (`queued`, `done`, `failed` or `skipped`) and `last_error`.
