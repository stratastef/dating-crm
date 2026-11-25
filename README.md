# Dating CRM

Product spec: [Dating CRM Spec.md](Dating%20CRM%20Spec.md). Agent docs: `CLAUDE.md`, `docs/agents/`.

## Layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app factory `create_app()` |
| `app/worker.py` | Worker process entry point |
| `app/db.py` | `database_url()`, read from `DATABASE_URL` |
| `app/auth.py` | `CurrentUser` and `Db` route dependencies, `create_user()` |
| `app/tenancy.py` | `user_id_column()` for tenant tables |
| `app/audit.py` | `record_action()` and `GET /audit-log` |
| `migrations/versions/` | Alembic migrations |
| `tests/` | pytest suite |
| `compose.yaml` | `db`, `api` and `worker` services |

Requirements: Docker, [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

## Run the stack

```sh
docker compose up --build
```

This starts Postgres, the API on <http://localhost:8000> and the worker. The API container runs `alembic upgrade head` before it starts.

`GET /health` returns `200 {"status": "ok"}` when Postgres is reachable, and `503` when it is not.

If port 5432 or 8000 is taken, set `DB_PORT` or `API_PORT`, for example `DB_PORT=5433 docker compose up`.

## Run the tests

The tests need a real Postgres server. They reach it through `DATABASE_URL`, which defaults to the Compose database on `localhost:5432`.

```sh
docker compose up -d --wait db
uv run pytest
```

Each test run creates its own database (`test_<random>`) on that server, migrates it to head and drops it at the end. The development database is not touched, and runs from several worktrees can share one server. If you start a second Compose stack from another worktree, give it its own port and point the tests at it: `DB_PORT=5433 docker compose up -d --wait db`, then `DATABASE_URL=postgresql+psycopg://app:app@localhost:5433/app uv run pytest`. Compose names containers after the directory, so worktrees do not clash on container names.

Fixtures in `tests/conftest.py`:

| Fixture | Gives you |
| --- | --- |
| `client` | `TestClient` authenticated as a fresh user. All tables are emptied after each test. |
| `client_for(email)` | Same, for a named user. Use it when a test needs two users. |
| `app` | The FastAPI app, for unauthenticated requests: `TestClient(app)`. |

## Authentication and tenancy

Each user has one opaque API token. The client sends `Authorization: Bearer <token>`. Only the SHA-256 of the token is stored. Create a user and print their token once:

```sh
uv run python -m app.auth you@example.com
```

In a route, declare `user: CurrentUser` and `db: Db` (both from `app.auth`). `CurrentUser` rejects the request with `401` unless the token is valid. `Db` is a SQLAlchemy connection in one transaction per request.

```python
@app.get("/matches")
def matches(user: CurrentUser, db: Db):
    return db.execute(text("SELECT ... FROM matches WHERE user_id = :user_id"), {"user_id": user.id})
```

Every table except `users` is a tenant table. Declare its owner with `user_id_column()` from `app.tenancy` in the migration, and filter every query by `user.id`. A test fails if a table has no `user_id` column.

```python
op.create_table("matches", sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True), user_id_column(), ...)
```

## Audit log

Every autopilot action must call `record_action(connection, user_id, type=..., app=..., target=..., trigger=...)` from `app.audit`, in the same transaction as the action. `type` is one of `message`, `like`, `pass`, `profile_change`, `calendar_hold`.
The `audit_log` table is append-only (a trigger rejects `UPDATE` and `DELETE`). `GET /audit-log?app=&type=` lists the current user's entries, newest first.

## Add a migration

```sh
uv run alembic revision -m "create matches table"  # writes a file in migrations/versions/
uv run alembic upgrade head                        # applies it to DATABASE_URL
```

Write `upgrade()` and `downgrade()` by hand. There are no ORM models yet, so `--autogenerate` finds nothing.

## Add a dependency

```sh
uv add <package>          # runtime
uv add --dev <package>    # test only
```

Commit `uv.lock`.

## CI

`.github/workflows/ci.yml` runs `uv run pytest` against a Postgres service on every push and pull request.
