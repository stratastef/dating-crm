# Dating CRM

Product spec: [Dating CRM Spec.md](Dating%20CRM%20Spec.md). Agent docs: `CLAUDE.md`, `docs/agents/`.

## Layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app factory `create_app()` |
| `app/worker.py` | Worker process entry point |
| `app/modules.py` | Imports every module in `app/`: a module joins the API by defining `router`, the worker by using `@handler` |
| `app/jobs.py` | Job queue: `enqueue()`, `@handler`, `run_once()`, `enqueue_recurring()` |
| `app/db.py` | `database_url()`, read from `DATABASE_URL` |
| `app/auth.py` | `CurrentUser` and `Db` route dependencies, `create_user()`, `issue_token()` |
| `app/sign_in.py` | Sign-in by phone number and sign-in code: `POST /sign-in/code`, `POST /sign-in`, `POST /sign-out` |
| `app/sms.py` | `send()`, the only way to text a phone |
| `app/cards.py` | Match cards and their messages: routes under `/cards` |
| `app/card_lookup.py` | Shared reads of one card: `own_card()`, `find_card()`, `conversation()`, `chat_lines()`, `unanswered()` |
| `app/llm.py` | `call()`, the only way to call Claude; records each call's cost |
| `app/jev.py` | Jev checks: `ask()`, the only way to call Jev, and the guardrail, handover, match-read, hot-lead and dealbreaker checks built on it |
| `app/budget.py` | The monthly AI budget: `GET` and `PUT /budget` |
| `app/drafts.py` | Copilot drafts for a card and the user's edits: `POST /cards/{id}/drafts`, `PATCH /drafts/{id}` |
| `app/screenshots.py` | Screenshot copilot: `POST /screenshots` reads a shared screenshot into a card and a draft |
| `app/reads.py` | The match read: inferences about a match, the user's corrections, card photos and the protected-trait opt-in |
| `app/send.py` | Sending a draft: `POST /drafts/{id}/send`, `queue_send()` and the `send_draft` job |
| `app/voice.py` | Questionnaire, style profile and similar past chats: routes under `/voice` |
| `app/bios.py` | Bio and prompt rewrites per dating app: routes under `/bios` |
| `app/photos.py` | The user's own photos, their ranking and light edits: routes under `/photos` |
| `app/preferences.py` | What the user wants, versioned: routes under `/preferences`, `current_preferences()` |
| `app/dashboard.py` | Good dates per hour, weekly: `POST /time` and `GET /dashboard` |
| `app/feedback.py` | Feedback loop: `swipe_lines()` for the swipe pre-screen prompt, and `GET /feedback/export` |
| `app/settings.py` | User settings: `GET` and `PATCH /settings`, `user_zone()` |
| `app/today.py` | Today: `GET /today`, the review summary and what the user has to do by time |
| `app/tenancy.py` | `user_id_column()` for tenant tables |
| `app/vault.py` | `store_token()`, `read_token()`, `delete_token()` for encrypted dating-app session tokens |
| `app/audit.py` | `record_action()` and `GET /audit-log` |
| `app/autopilot.py` | Autonomy per job and Pause: `autopilot_allowed()`, `pause()`, `resume()` |
| `app/connectors.py` | `Connector` contract, `call()`, `is_copilot_only()`, `alerts()` |
| `app/push.py` | `send_push()` and `POST /devices` |
| `app/calendar.py` | Google Calendar: routes under `/calendar`, `free_slots()`, `hold_slot()`, `release_holds()`, `confirm_date()` |
| `app/review.py` | Review queue: `GET /queue`, approve and dismiss a draft, `is_hot_lead()` |
| `app/handover.py` | Handover: pauses a card on a handover trigger, suggested replies, take-over and hand-back, `is_paused()` |
| `app/chat_autopilot.py` | Chat autopilot: the `chat_reply` job, `GET` and `PUT /settings/ai-disclosure` |
| `app/tinder.py` | `TinderConnector`: reads matches and messages from Tinder's unofficial web API |
| `app/sync.py` | `PUT /connectors/{app}/token`, Connected apps (`GET /connectors`, `PUT /connectors/{app}/copilot-only`) and the `sync_matches` job |
| `app/purge.py` | Find and purge: `GET /people`, `GET /people/candidates`, `POST /people/purge` |
| `app/tombstones.py` | `bury()` and `is_buried()`: a purged person is not stored again |
| `app/paid_items.py` | Paid items (Super Like, Rose, Boost): `propose()`, approve and decline routes, and `spend()`, the only code that spends one |
| `app/swipes.py` | Swipe copilot (like or pass suggestions and the user's swipes, routes under `/swipes`) and swipe autopilot (the `swipe_autopilot` job) |
| `migrations/versions/` | Alembic migrations |
| `tests/` | pytest suite |
| `compose.yaml` | `db`, `api` and `worker` services |
| `ios/` | SwiftUI app. See [ios/README.md](ios/README.md). |

Requirements: Docker, [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

## Module docs

Read the doc for a module before you change it or call it. Review rules live in `CODING_STANDARDS.md`.

- [Cards and messages](docs/modules/cards-and-messages.md)
- [Background jobs](docs/modules/background-jobs.md)
- [Calling Claude](docs/modules/calling-claude.md)
- [Voice](docs/modules/voice.md)
- [Bios](docs/modules/bios.md)
- [Photos](docs/modules/photos.md)
- [Drafts](docs/modules/drafts.md)
- [Jev checks](docs/modules/jev-checks.md)
- [Review queue](docs/modules/review-queue.md)
- [Match read](docs/modules/match-read.md)
- [Screenshot import](docs/modules/screenshot-import.md)
- [Handover](docs/modules/handover.md)
- [Chat autopilot](docs/modules/chat-autopilot.md)
- [Preferences](docs/modules/preferences.md)
- [Dashboard](docs/modules/dashboard.md)
- [Session token vault](docs/modules/session-token-vault.md)
- [Audit log](docs/modules/audit-log.md)
- [Find and purge](docs/modules/find-and-purge.md)
- [Autonomy and Pause](docs/modules/autonomy-and-pause.md)
- [Connectors](docs/modules/connectors.md)
- [Push notifications](docs/modules/push-notifications.md)
- [Google Calendar holds](docs/modules/google-calendar-holds.md)
- [Sync](docs/modules/sync.md)
- [Swipe copilot](docs/modules/swipe-copilot.md)
- [Feedback loop](docs/modules/feedback-loop.md)
- [Swipe autopilot](docs/modules/swipe-autopilot.md)
- [Paid items](docs/modules/paid-items.md)
- [Tinder connector](docs/modules/tinder-connector.md)
- [iOS app shell and shared components](docs/modules/ios-app-shell.md)
- [Sign-in](docs/modules/sign-in.md)
- [Today](docs/modules/today.md)

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
| `llm` | The stub that replaces `app.llm.complete` in every test. See "Calling Claude". |
| `apns` | The stub that replaces `app.push.post` in every test. See "Push notifications". |
| `jev` | The stub that replaces `app.jev.ask` in every test. See "Jev checks". |
| `gcal` | The stub that replaces `app.calendar.google` in every test. See "Google Calendar holds". |
| `sms` | The stub that replaces `app.sms.send` in every test. See "Sign-in". |

## Authentication and tenancy

Each signed-in device has its own opaque API token, which the app gets by signing in with a phone number and a sign-in code (see [Sign-in](docs/modules/sign-in.md)). The client sends `Authorization: Bearer <token>`. Only the SHA-256 of the token is stored. Create a user and print a token once, for the developer sign-in:

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

## Add a migration

```sh
uv run alembic revision -m "create matches table" --rev-id t42_matches  # t<ticket>_<slug>, no sequence number
uv run alembic upgrade head                                             # applies it to DATABASE_URL
```

Write `upgrade()` and `downgrade()` by hand. There are no ORM models yet, so `--autogenerate` finds nothing. Name the revision after its ticket: sequence numbers collide when tickets are built in parallel. `scripts/merge-ticket <branch>` merges a ticket branch and re-points its migration onto the current head.

## Add a dependency

```sh
uv add <package>          # runtime
uv add --dev <package>    # test only
```

Commit `uv.lock`.

## CI

`.github/workflows/ci.yml` runs four jobs on every push and pull request: `test` (`uv run pytest` against Postgres), `lint` (`uv run ruff check .` and `uv run pyright`), `stack` (builds the images, starts Compose and calls `/health`) and `ios` (`xcodebuild test`). Run the first two locally before you report a ticket done.
