# Dating CRM

Product spec: [Dating CRM Spec.md](Dating%20CRM%20Spec.md). Agent docs: `CLAUDE.md`, `docs/agents/`.

## Layout

| Path | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app factory `create_app()` |
| `app/worker.py` | Worker process entry point |
| `app/jobs.py` | Job queue: `enqueue()`, `@handler`, `run_once()`, `enqueue_recurring()` |
| `app/db.py` | `database_url()`, read from `DATABASE_URL` |
| `app/auth.py` | `CurrentUser` and `Db` route dependencies, `create_user()` |
| `app/cards.py` | Match cards and their messages: routes under `/cards` |
| `app/llm.py` | `complete()`, the only function that calls Claude |
| `app/voice.py` | Questionnaire, style profile and similar past chats: routes under `/voice` |
| `app/bios.py` | Bio and prompt rewrites per dating app: routes under `/bios` |
| `app/preferences.py` | What the user wants, versioned: routes under `/preferences`, `current_preferences()` |
| `app/settings.py` | User settings: `GET` and `PATCH /settings` |
| `app/tenancy.py` | `user_id_column()` for tenant tables |
| `app/vault.py` | `store_token()`, `read_token()`, `delete_token()` for encrypted dating-app session tokens |
| `app/audit.py` | `record_action()` and `GET /audit-log` |
| `app/autopilot.py` | Autonomy per job and the kill switch: `autopilot_allowed()`, `pause()`, `resume()` |
| `app/connectors.py` | `Connector` contract, `call()`, `is_copilot_only()`, `alerts()` |
| `app/tinder.py` | `TinderConnector`: reads matches and messages from Tinder's unofficial web API |
| `app/sync.py` | `PUT /connectors/{app}/token` and the `sync_matches` job |
| `migrations/versions/` | Alembic migrations |
| `tests/` | pytest suite |
| `compose.yaml` | `db`, `api` and `worker` services |
| `ios/` | SwiftUI app. See [ios/README.md](ios/README.md). |

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
| `llm` | The stub that replaces `app.llm.complete` in every test. See "Calling Claude". |

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

## Cards and messages

A card is one match. Routes are in `app/cards.py`; tables are `cards` and `messages`. All routes need a token and see only the caller's rows; a card that is not yours is `404`.

| Route | Does |
| --- | --- |
| `POST /cards` | Create a card. Body: `app`, `name`, optional `external_id`, `stage` (default `matched`), `notes`, `next_action`, `due_date`. |
| `GET /cards?stage=&app=` | List cards, oldest first. Both filters are optional. |
| `GET /cards/{id}` | Read one card. |
| `PATCH /cards/{id}` | Change only the fields sent: `name`, `stage`, `notes`, `next_action`, `due_date`. `null` clears `next_action` or `due_date`. |
| `POST /cards/{id}/messages` | Add a message. Body: `sender` (`me` or `them`), `body`, optional `sent_at` (default now), `external_id`. |
| `GET /cards/{id}/messages` | List the card's messages by `sent_at`. |

- `stage` is one of `matched`, `chatting`, `number_swapped`, `date_set`, `dated`, `seeing_them`, `archived`. Anything else is `422`. `stage_changed_at` on the card is the time of the last stage change; there is no stage history table.
- Stalled is a flag on the card, not a stage. The hourly `mark_stalled` job sets `stalled: true` on a card in `chatting`, `number_swapped` or `date_set` whose last message, from either side, is older than the user's `stalled_after_days` (a card with no messages counts from `stage_changed_at`). A stalled card has `suggested_actions: ["revive", "archive"]`; otherwise the list is empty. A new message from `them` clears the flag, and so does moving the card out of those three stages; archive is `PATCH /cards/{id}` with `stage: archived`.
- `GET /settings` and `PATCH /settings` read and change the user's settings. `stalled_after_days` is a whole number of days, at least 1, default 3.
- `PATCH /cards/{id}` also takes `date_rating` (1 to 5) and `date_note`, both null until the user rates the date. A good date is a rating of 4 or 5: `is_good_date()` in `app/cards.py` is the only definition, and the card's `good_date` field is its result.
- `app` is free text, for example `tinder` or `hinge`.
- `external_id` is the ID the dating app gives the match or message. It is unique per user and app for cards, and per card for messages; a duplicate is `409`. Rows without one are never duplicates.

## Background jobs

Jobs are rows in the `jobs` table. The API enqueues them and only the worker runs them. Both functions are in `app/jobs.py`.

Enqueue inside the request transaction. The job is queued only if the request commits. `run_at` is optional and schedules the job for later:

```python
job_id = enqueue(db, user.id, "sync_matches", {"app": "tinder"}, run_at=tomorrow)
```

Register one handler per kind, and import its module in `app/worker.py`:

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

## Calling Claude

All Claude calls go through one function, `complete()` in `app/llm.py`, which uses the `anthropic` SDK. Call it through the module so tests can replace it:

```python
from app import llm

result = llm.complete(system="...", prompt="...")  # result.text, result.model, result.input_tokens, result.output_tokens
```

- The model is read from `ANTHROPIC_MODEL` (default `claude-fable-5-2`) and the key from `ANTHROPIC_API_KEY`. Compose passes both to the API and worker.
- Every call returns its token usage. Nothing stores it yet.
- A refusal raises `RuntimeError`. Server-side fallback models are not configured.
- Tests never reach the API: the autouse `llm` fixture in `tests/conftest.py` replaces `complete()` with a stub. Set `llm.reply` to choose the text and read `llm.prompts` to see what was sent.

## Voice

Routes and the job are in `app/voice.py`; the table is `voice_profiles` (one row per user).

| Route | Does |
| --- | --- |
| `PUT /voice/questionnaire` | Replace the questionnaire answers. Body: `{"answers": {"<question>": "<answer>"}}`. |
| `GET /voice` | Read `answers` and `profile`. `profile` is `null` until the worker has written it. |
| `GET /cards/{id}/similar-chats?limit=` | Past chats that led to a date, most similar to this card's conversation first. `limit` defaults to 3. |

- The `voice_profile` job writes the style profile from the answers and the user's own messages (the newest 200). Saving answers and `POST /cards/{id}/messages` with `sender: me` queue it. Code that stores messages another way must call `queue_profile(db, user_id)`.
- A chat led to a date if its card's stage is `date_set`, `dated` or `seeing_them`.
- Similarity is `similarity()` from the Postgres `pg_trgm` extension over the whole chat text, so it measures shared wording, not meaning. Other code calls `similar_chats(db, user_id, card_id, limit)`.

## Bios

Routes are in `app/bios.py`; the table is `bios` (one row per user and app). A bio is `{"bio": "...", "prompts": {"<prompt>": "<answer>"}}`.

| Route | Does |
| --- | --- |
| `POST /bios/{app}/rewrite` | Rewrite the bio in the body for that app from the style profile. Returns the rewrite and stores nothing. |
| `PUT /bios/{app}` | Store the version the user accepted for that app, replacing the previous one. |
| `GET /bios/{app}` | Read the accepted version. Empty until one is accepted. |

- To regenerate, call the rewrite route again. To regenerate from an edit, send the edited text as the body.
- The rewrite route returns `409` until the style profile is written, and `502` if Claude's reply is not a bio; the client can retry.
- Nothing is written to a dating app: in copilot the user copies the accepted text.

## Preferences

Routes are in `app/preferences.py`; the table is `preferences` (append-only, one row per saved version). Preferences are `{"wishes": "...", "must_haves": ["..."], "dealbreakers": ["..."]}`.

| Route | Does |
| --- | --- |
| `GET /preferences` | The version in force, with its `version` number. Version `0` and empty until the first save. |
| `PUT /preferences` | Store the body as the next version. Earlier versions are kept. |
| `GET /preferences/versions` | Every version, oldest first, each with `created_at`: the moment it came into force. |

Server code reads the version in force with `current_preferences(db, user_id)` from `app.preferences`; it returns `version`, `wishes`, `must_haves` and `dealbreakers`.

## Session token vault

Dating-app session tokens go through `app/vault.py` and nowhere else: `store_token(db, user.id, "tinder", token)`, `read_token(db, user.id, "tinder")` (returns `None` if absent), `delete_token(db, user.id, "tinder")`.

Each user has their own key in `vault_keys`, encrypted with the master key. The master key is read from `TOKEN_VAULT_MASTER_KEY` and is never stored in the database. Without it the vault raises `KeyError`. If it is lost, stored tokens cannot be recovered. Generate one:

```sh
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Compose passes `TOKEN_VAULT_MASTER_KEY` from your shell or `.env` to the API and worker. Never log a token value.

## Audit log

Every autopilot action must call `record_action(connection, user_id, type=..., app=..., target=..., trigger=...)` from `app.audit`, in the same transaction as the action. `type` is one of `message`, `like`, `pass`, `profile_change`, `calendar_hold`.
The `audit_log` table is append-only (a trigger rejects `UPDATE` and `DELETE`). `GET /audit-log?app=&type=` lists the current user's entries, newest first.

## Autonomy and kill switch

All in `app/autopilot.py`. Each job (`chat`, `profile`, `swipe`) has a level: `off`, `copilot`, `guardrails` or `full`. Chat and profile default to `copilot`, swipe to `off`. A pause stops autopilot for one app or for all apps.

| Route | Does |
| --- | --- |
| `GET /autonomy` | Level per job |
| `PUT /autonomy/{job}` with `{"level": "full"}` | Sets one level |
| `GET /autopilot/pause` | `{"all": false, "apps": ["tinder"]}` |
| `POST /autopilot/pause?app=tinder`, `POST /autopilot/resume?app=tinder` | Pauses or resumes one app. Without `app`: all apps. |

From code, with `app=None` meaning all apps:

```python
pause(db, user_id, "tinder", reason="ban signal")  # the reason is recorded on skipped jobs
resume(db, user_id, "tinder")
autopilot_allowed(db, user_id, "tinder", "chat")   # False if paused, or if chat autonomy is off or copilot
```

Resuming all apps lifts only the pause on all apps. An app paused on its own stays paused until it is resumed by name.

Mark a job handler as autopilot with the job it acts for, and put the app in the payload as `"app"`:

```python
@handler("send_reply", autopilot="chat")
def send_reply(db: Connection, user_id: int, payload: dict) -> None: ...
```

The worker runs such a job only if `autopilot_allowed()` is true at that moment. Otherwise it sets the job's status to `skipped` and writes the reason to `last_error`. Skipped jobs are not retried. Handlers that draft for copilot are not autopilot jobs: leave `autopilot` unset.
## Connectors

The contract is in `app/connectors.py`. The capabilities are `read_matches`, `read_messages`, `send`, `like` and `pass`.

Add a connector: subclass `Connector`, set `app`, declare the `capabilities` it supports and implement the method for each one (`pass` is the method `pass_`). Leave a capability out of `capabilities` to leave it out of the build. Each method receives the session token as its first argument. A method raises any exception when the app refuses or breaks.

```python
class TinderConnector(Connector):
    app = "tinder"
    capabilities = frozenset({"read_matches", "read_messages"})

    def read_matches(self, token: str) -> list[dict]: ...
    def read_messages(self, token: str, match_id: str) -> list[dict]: ...
```

Never call a connector method directly. Go through `call()`, which reads the user's token from the vault, passes it to the method and enforces the rules below:

```python
matches = call(db, user_id, TinderConnector(), "read_matches")
messages = call(db, user_id, TinderConnector(), "read_messages", match_id)
```

- **Switch a capability off:** set `CONNECTOR_DISABLED_CAPABILITIES=tinder:send,hinge:like` (comma-separated `app:capability`).
- **Unavailable:** `call()` raises `CapabilityUnavailable` and does not touch the app when the capability is not declared, is disabled, the app is copilot-only, or the user has no stored token for the app.
- **Fallback to copilot:** if the connector method raises, `call()` inserts a row in `connector_alerts` (`user_id`, `app`, `capability`, `error` = `repr()` of the exception) and raises `CapabilityFailed`, with the connector's exception as `__cause__`. The row is written in its own transaction, so it survives the failed job's rollback. That row is both the alert and the fallback: `is_copilot_only(db, user_id, app)` is true while the user has any alert for the app, and every capability of that app is then unavailable for that user. `alerts(db, user_id)` lists them. Delete the user's rows for an app to re-enable its connector.
- **Ban detection:** `classify(error)` sorts the connector's exception into `auth failure` (HTTP 401), `ban signal` (HTTP 403) or `transient` (anything else), stored in the alert's `reason`. An auth failure or ban signal also calls `pause(user_id, app, reason)` in the same transaction as the alert, so that app's autopilot stops for that user; a transient error does not pause. `GET /connectors/alerts` returns the user's alerts (`id`, `app`, `capability`, `reason`, `error`, `created_at`), newest first. A fresh token lifts the copilot-only fallback but not the pause: resume with `POST /autopilot/resume?app=...`.

Test a connector's callers with a fake like `FakeConnector` in `tests/test_connectors.py`.

## Sync

`app/sync.py` copies an app's matches and messages into cards. It works for every connector listed in `CONNECTORS` there.

- **Start:** `PUT /connectors/{app}/token` with `{"token": "..."}` stores the token in the vault, deletes the user's alerts for the app (so the connector is on again) and queues a `sync_matches` job with payload `{"app": app}`. It returns `204`, or `404` if the app has no connector.
- **Schedule:** `sync_matches` is a recurring job (`every=SYNC_INTERVAL`, 15 minutes). The recurring run has an empty payload and syncs every app in `CONNECTORS`. It skips an app, without failing, when the user has no token for it, the app is copilot-only or a read capability is switched off.
- **Cards:** a new match becomes a card in `matched`. `upsert_card()` in `app/cards.py` finds the card by `external_id`; on a later sync it changes only the name.
- **Messages:** `upsert_message()` adds a message unless the card already has its `external_id`. A new message moves a card from `matched` to `chatting`. Sync never changes any other stage.
- **Fewer requests:** sync reads a match's messages only when the match has messages and its newest one is not stored yet.
- **Not built:** a match that disappears from the app (unmatched) keeps its card and stage.

A connector's `read_matches` returns dicts with `id`, `name`, `has_messages` and `last_message_id` (`None` if unknown). Its `read_messages` returns dicts with `id`, `sender` (`me` or `them`), `body` and `sent_at`.

## Tinder connector

`app/tinder.py` reads your own Tinder account with your own web session token. It supports `read_matches` and `read_messages` only. Tinder's terms do not allow this API use; see Risks in the spec.

### Capture and submit your token

1. On your computer, log in at <https://tinder.com> in a desktop browser.
2. Open the developer tools (F12), then the Network tab, and reload the page.
3. Click any request to `api.gotinder.com` and copy the value of the `X-Auth-Token` request header. The same value is in Application > Local Storage > `https://tinder.com` under the key `TinderWeb/APIToken`.
4. Send it to your server. `$API_TOKEN` is your Dating CRM token from `python -m app.auth`:

```sh
curl -X PUT http://localhost:8000/connectors/tinder/token \
  -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"token": "<the X-Auth-Token value>"}'
```

The worker syncs within a second and then every 15 minutes. Check with `GET /cards?app=tinder`. The token is a password for your Tinder account: do not paste it anywhere else. When Tinder logs the web session out, one sync fails, the app becomes copilot-only and an alert is stored. Later syncs skip Tinder until you repeat the steps.

### Assumptions to confirm against your real account

The connector was built from public write-ups of the web API and was never run against Tinder. The fixtures in `tests/fixtures/tinder/` are written by hand in that shape; they are not recordings. Compare each row with a real response in the Network tab and fix `app/tinder.py` and the fixtures where they differ.

| Assumption | Used for |
| --- | --- |
| The token is in `localStorage` as `TinderWeb/APIToken` and is sent as the `X-Auth-Token` header | Capture, every request |
| `X-Auth-Token` is the only header Tinder requires (no `app-version`, `platform` or device ID headers) | Every request |
| `GET https://api.gotinder.com/v2/matches?count=60&message=0` lists matches without messages, and `message=1` those with messages | `read_matches`, `has_messages` |
| `count=60` is accepted on both endpoints | Page size |
| The response body is `{"data": {"matches": [...], "next_page_token": "..."}}`, and `next_page_token` is absent on the last page and sent back as `page_token` | Paging |
| A match has `_id` and `person._id`, `person.name` | Card `external_id` and name, telling senders apart |
| A match from `message=1` has `messages`, a list that includes its newest message, each with `_id` and `sent_date` | `last_message_id`. If the list is missing or empty, sync reads that match's messages on every run. If it holds only older messages, sync misses new ones |
| `GET /v2/matches/{match_id}/messages?count=60` returns `{"data": {"messages": [...], "next_page_token": "..."}}` | `read_messages` |
| A message has `_id`, `from` (a user ID), `message` (the text) and `sent_date` (ISO 8601) | Message `external_id`, sender, body, time |
| A message whose `from` is not `person._id` is yours | `sender` |
| An expired token gives HTTP `401` | Fallback to copilot |
| One sync every 15 minutes does not trip Tinder's rate limits or bot detection | `SYNC_INTERVAL` |

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
