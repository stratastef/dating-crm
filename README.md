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
| `app/llm.py` | `call()`, the only way to call Claude; records each call's cost |
| `app/budget.py` | The monthly AI budget: `GET` and `PUT /budget` |
| `app/drafts.py` | Copilot drafts for a card and the user's edits: `POST /cards/{id}/drafts`, `PATCH /drafts/{id}` |
| `app/screenshots.py` | Screenshot copilot: `POST /screenshots` reads a shared screenshot into a card and a draft |
| `app/reads.py` | The match read: inferences about a match, the user's corrections, card photos and the protected-trait opt-in |
| `app/send.py` | Sending a draft: `POST /drafts/{id}/send`, `queue_send()` and the `send_draft` job |
| `app/voice.py` | Questionnaire, style profile and similar past chats: routes under `/voice` |
| `app/bios.py` | Bio and prompt rewrites per dating app: routes under `/bios` |
| `app/preferences.py` | What the user wants, versioned: routes under `/preferences`, `current_preferences()` |
| `app/dashboard.py` | Good dates per hour, weekly: `POST /time` and `GET /dashboard` |
| `app/settings.py` | User settings: `GET` and `PATCH /settings` |
| `app/tenancy.py` | `user_id_column()` for tenant tables |
| `app/vault.py` | `store_token()`, `read_token()`, `delete_token()` for encrypted dating-app session tokens |
| `app/audit.py` | `record_action()` and `GET /audit-log` |
| `app/autopilot.py` | Autonomy per job and the kill switch: `autopilot_allowed()`, `pause()`, `resume()` |
| `app/connectors.py` | `Connector` contract, `call()`, `is_copilot_only()`, `alerts()` |
| `app/push.py` | `send_push()` and `POST /devices` |
| `app/calendar.py` | Google Calendar: routes under `/calendar`, `free_slots()`, `hold_slot()`, `release_holds()`, `confirm_date()` |
| `app/review.py` | Review queue: `GET /queue`, approve and dismiss a draft, `is_hot_lead()` |
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
| `apns` | The stub that replaces `app.push.post` in every test. See "Push notifications". |
| `jev` | The stub that replaces `app.jev.ask` in every test. See "Jev checks". |

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

All Claude calls go through one function, `call()` in `app/llm.py`. It sends the prompt with the `anthropic` SDK (`complete()`) and records what the call cost. Never call `complete()` directly: the cost would not be recorded.

```python
from app import llm

result = llm.call(db, user.id, "draft", system="...", prompt="...")  # result.text, result.model, result.input_tokens, result.output_tokens
```

- To show Claude images, pass `images=[...]`. An item is an `https` URL that Claude fetches, or `("image/png", data)` (media type and bytes) to send the picture itself.

- The model is read from `ANTHROPIC_MODEL` (default `claude-fable-5-2`) and the key from `ANTHROPIC_API_KEY`. Compose passes both to the API and worker.
- Every call inserts one row in `llm_calls`: `purpose` (the third argument, naming the feature), `model`, both token counts and `cost_usd`. The row is written in its own transaction, so it is kept when the calling job fails. `llm.spend(db, user_id)` is the user's total for the current calendar month (UTC) in USD.
- **AI budget:** each user has a hard monthly cap, `users.ai_budget_usd`, default 50 USD. `GET /budget` returns `{"spend_usd", "cap_usd", "paused"}` and `PUT /budget` with `{"cap_usd": 20}` sets the cap (routes in `app/budget.py`). While the month's spend is at the cap, `call()` raises `llm.BudgetReached` without calling Claude (a route answers `402`; a job retries and then fails), and the worker skips autopilot jobs with the reason `AI budget reached`. The call that reaches the cap sends the user a push. The budget pause is computed, not a row in `autopilot_pauses`: a new month or a higher cap lifts it, `POST /autopilot/resume` does not, and it is not shown by `GET /autopilot/pause`. Pauses set for other reasons are untouched. Spend can pass the cap by the cost of calls already in flight.
- Cost is tokens times the per-model price in `llm.PRICES` (USD per million tokens). The prices are copied by hand: confirm them against Anthropic's price list. A model missing from the table is charged at the default model's price.
- A refusal raises `RuntimeError`. Server-side fallback models are not configured.
- Tests never reach the API: the autouse `llm` fixture in `tests/conftest.py` replaces `complete()` with a stub. Set `llm.reply` to choose the text and read `llm.prompts`, `llm.systems` and `llm.images` to see what was sent. For a route that calls Claude more than once, set `llm.replies` to a list; it is used up first, one per call.

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

## Drafts

Routes are in `app/drafts.py`; the table is `drafts` (one row per draft).

| Route | Does |
| --- | --- |
| `POST /cards/{id}/drafts` | Have Claude write a draft for the card and store it. `kind` is `opener` when the card has no messages, else `reply`. |
| `PATCH /drafts/{id}` | Store the user's edit. Body: `{"edited": "..."}`. |
| `POST /drafts/{id}/send` | The user approves the draft: queue it for the worker to send. Returns `202` and the draft. In `app/send.py`. |

- A draft is `{"id", "card_id", "kind", "status", "original", "edited"}`. `original` is Claude's text and never changes; `edited` is `null` until the user edits. The text to use is `edited` if set, else `original`.
- `status` is `pending` until the user sends, approves or dismisses the draft (see "Review queue"). A sent or approved draft is `approved` (queued), then `sending` (the worker is sending it) and `sent` or `failed`. A dismissed draft is `dismissed`. The user can still copy any draft.
- **Send:** the route answers `409` with the reason and queues nothing when the draft is not `pending`, the card's app is paused (the kill switch, for that app or all apps), the app has no connector, the card has no `external_id`, or `send` is unavailable (see "Connectors": not declared, switched off, copilot-only, no token).
- **Queue a send from code:** `queue_send(db, user_id, draft_id, trigger)` in `app/send.py` is the one way to send a draft. It moves a `pending` draft to `approved` and queues a `send_draft` job in your transaction; it returns the draft, or `None` if the draft is not `pending`. `trigger` goes to the audit log. It does not check the pause or autonomy: the route checks the pause before it, and the job checks the pause again. The review queue approves the draft itself, so it calls `send_approved(db, user_id, draft_id, trigger)`, which queues the job for an already `approved` draft if the app can send.
- **The `send_draft` job** sends the text (`edited` if set, else `original`) with the connector's `send`, stores the message on the card under the app's message ID (so sync does not add it twice), writes an audit log entry (`type: message`, `target: card:<id>`) and sets `sent`. If the app became paused or `send` unavailable after the tap, nothing is sent and the draft goes back to `pending`.
- **At most once:** the job commits `sending` before it calls the app. If the app answers with an error, or the worker dies before the job commits, the draft ends as `failed` and is never sent again, because the message may have gone out. A `failed` draft whose message did go out appears on the card at the next sync. To try again, write another draft.
- The prompt holds the style profile, the card's app, name and notes, the match read (its `tone` sets the draft's tone), the conversation, and `similar_chats()` as examples.
- The write route returns `409` until the style profile is written, and `502` if Claude's reply is empty.
- A draft also has `guardrail` and `hot_lead`, the results of its Jev checks (see below).

## Jev checks

Jev is a cheap yes/no classifier reached through treg. It judges one sentence at a time and never sees the rest of the chat. All of it is in `app/jev.py`; `ask()` is the one function that calls Jev.

| Function | Use it for | Returns |
| --- | --- | --- |
| `jev.ask(sentence, check)` | One yes/no check on one sentence. `check` is a key of `jev.CHECKS`; add a key to add a check, for example a bio dealbreaker. | `bool`. Raises `JevUnavailable` when Jev is not configured or the call fails. |
| `jev.guardrail_hits(text)` | Draft guardrail on an outgoing message. | The checks hit, from `denies_ai`, `protected_trait`, `overpromise`. Empty means safe to send. |
| `jev.handover_hits(text)` | Handover trigger on an incoming message. | The checks hit, from `asks_if_ai`, `logistics`, `personal_info`, `sensitive`. Empty means no handover. |
| `jev.is_hot_lead(text)` | Hot-lead triage on a draft. | `bool`: the draft deserves a live push. |

- The three functions split the text into sentences and ask about each. A check is hit if any sentence hits it.
- Results are stored with the row. `messages.handover` is set for every new message from `them`, by `POST /cards/{id}/messages` and by `upsert_message`; it is `null` for the user's own messages. `drafts.guardrail` and `drafts.hot_lead` are set when a draft is written, and `PATCH /drafts/{id}` runs the guardrail again on the edit. The routes return these fields.
- Never send a draft whose `guardrail` is not an empty list. Code that sends any other text must call `jev.guardrail_hits()` on it first.
- Fail closed: when Jev is not configured or a call fails, `guardrail_hits` and `handover_hits` return `["unavailable"]`, which counts as a hit, and `is_hot_lead` returns `False`. Nothing is sent unattended without Jev.
- The owner must set three variables for the API and the worker; Compose passes them through from your shell or `.env`. Until all three are set, every check fails closed as above.

| Variable | Fill in |
| --- | --- |
| `JEV_BASE_URL` | The treg server, for example `https://treg.to`. |
| `JEV_API_KEY` | Your treg token. It is sent as the `X-Treg-Token` header. |
| `JEV_TOOL` | The treg endpoint that reaches Jev, for example `openrouter.ai-judge.decide`. |
| `JEV_MODEL` | Optional. The Jev model, default `typesafe/jev-1.13`. |

- The request is `POST {JEV_BASE_URL}/call/{JEV_TOOL}` with one question of type `noul`; the answer is read from `answers.q1.noul` (a probability; 0.5 or more is yes). This shape is copied from treg's `jev-memory` example and has not been run against the real service: confirm it with one real call before relying on the checks.
- Jev calls are not recorded in `llm_calls`.
- Tests never reach Jev: the autouse `jev` fixture in `tests/conftest.py` replaces `ask()`. It answers no unless the sentence contains a phrase you list, `jev.yes["logistics"] = ["saturday"]`; `jev.asked` records each call.

## Review queue

All in `app/review.py`. A pending draft waits in the queue until the user approves or dismisses it; editing is `PATCH /drafts/{id}`.

| Route | Does |
| --- | --- |
| `GET /queue` | List what waits for the user, hot leads first, then oldest first. |
| `POST /drafts/{id}/approve` | Set the draft's `status` to `approved` and return it. `409` if it is no longer pending. |
| `POST /drafts/{id}/dismiss` | Set the draft's `status` to `dismissed` and return it. `409` if it is no longer pending. |

- A queue item is `{"kind", "hot", "card_id", "card_name", "draft"}`. `kind` is `draft` so far and `draft` holds the draft; a new kind of item adds its own `kind` and may leave `draft` null.
- `is_hot_lead(db, card_id)` is the only definition of a hot lead. So far: the match sent a message within the last hour, or Jev's hot-lead triage flagged a pending draft of the card (`drafts.hot_lead`). Add date-coordination and handover signals there.
- `POST /cards/{id}/drafts` calls `notify_if_hot()`, which sends one push at once for a hot lead and nothing otherwise. Call it wherever else an item joins the queue.
- Approving sends the draft when its card's app can send: `hand_on_approved_draft(db, user_id, draft)` is called once per approved draft and queues the `send_draft` job (see "Drafts"). When the app cannot send (no connector, paused, `send` unavailable, card without `external_id`), the approval still succeeds, the draft stays `approved` and the user copies it.

## Match read

Routes are in `app/reads.py`; the tables are `inferences` (one row per card and kind) and `card_photos`. Both are keyed by card, and deleting a card deletes its rows.

| Route | Does |
| --- | --- |
| `POST /cards/{id}/read` | Have Claude read the match from the notes, the conversation and the card's photos, and store the inferences. |
| `GET /cards/{id}/read` | The card's inferences. Empty until a read is made. |
| `PATCH /inferences/{id}` | Store the user's correction. Body: `{"corrected": "..."}`. |
| `POST /cards/{id}/photos` | Attach a photo of the match by `https` URL. Body: `{"url": "..."}`. Connectors and screenshot import can insert into `card_photos` directly. |
| `GET` and `PUT /settings/protected-trait-guesses` | Read or set the opt-in. Body: `{"enabled": true}`. Off by default. |

- An inference is `{"id", "card_id", "kind", "value", "evidence", "confidence", "corrected"}`. `kind` is `texting_style`, `interests`, `values`, `photos` or `tone`; `confidence` is 0 to 1. `value` is Claude's; the value to use is `corrected` if set, else `value`.
- A new read replaces the uncorrected inferences. A corrected one keeps its correction and gets Claude's new `value` next to it.
- `_allowed()` checks every inference Claude replies before it is stored, and drops it when: a field is missing, the evidence is empty or the confidence is outside 0 to 1; it is about anyone but the match (`about` is not `match`); it targets an insecurity; its kind is not listed above; or it guesses a protected trait (ethnicity, religion, health, sexuality, politics) and the user has not opted in. The `about`, `protected_trait` and `targets_insecurity` labels are Claude's own, so a mislabelled inference under an allowed kind gets through.
- With the opt-in on, a protected trait may also be its own kind (`religion` and so on). Opting out hides stored protected-trait inferences from the read and from drafts; it does not delete them.
- With no photos on the card the read is from text only.
- Other server code reads the card's read with `read_lines(db, user_id, card_id)`.
- The read route returns `502` if Claude's reply is not a JSON list; the last read is kept.

## Screenshot import

`POST /screenshots` in `app/screenshots.py` is the copilot path for every app, with or without a connector. The iOS share extension calls it.

- **Request:** the body is the image itself, with `Content-Type: image/png` or `image/jpeg`, at most 5 MB. Another type is `415`, a larger body `413`, an empty one `422`.
- **Read:** Claude reads the app, the match's name and the visible messages (`llm.call` with `purpose` `screenshot`). A reply that is not usable is `502`; the client can retry.
- **Card:** the user's card with the same app and name, ignoring case, else a new card in `matched`. An existing card keeps everything but gains messages.
- **Messages:** the screenshot usually repeats the end of the stored chat, so only what comes after that overlap is added, through `upsert_message()`.
- **Answer:** `201` with a draft for the card, as `POST /cards/{id}/drafts` returns it, including its `409` until the style profile is written. On any error no card, message or draft is stored.
- **Limits:** two matches with the same name on one app share a card. A screenshot of an older part of a chat is added again at the end. Message times are not read: new messages are stamped with the time of the import. The image is not kept. Reading a real screenshot with the real Claude API has not been tried; the tests use the stub.

## Preferences

Routes are in `app/preferences.py`; the table is `preferences` (append-only, one row per saved version). Preferences are `{"wishes": "...", "must_haves": ["..."], "dealbreakers": ["..."]}`.

| Route | Does |
| --- | --- |
| `GET /preferences` | The version in force, with its `version` number. Version `0` and empty until the first save. |
| `PUT /preferences` | Store the body as the next version. Earlier versions are kept. |
| `GET /preferences/versions` | Every version, oldest first, each with `created_at`: the moment it came into force. |

Server code reads the version in force with `current_preferences(db, user_id)` from `app.preferences`; it returns `version`, `wishes`, `must_haves` and `dealbreakers`.

## Dashboard

Routes are in `app/dashboard.py`; the table is `app_time` (one row per report).

| Route | Does |
| --- | --- |
| `POST /time` with `{"seconds": 90}` | Record time the user spent in the app. 1 second to 1 day per report; returns `204`. |
| `GET /dashboard` | One entry per week with recorded time or a good date, oldest first: `week` (its Monday), `good_dates`, `hours`, `good_dates_per_hour`. |

- A week starts on Monday in UTC. `good_dates_per_hour` is `null` for a week with no recorded time.
- A good date (`is_good_date()`) counts in the week of the card's `date_rated_at`: the moment of its first rating, not the day of the date.
- Limit: hours are only the time the iOS app was in the foreground, as the app reports it; time in the dating apps is not counted, and a stretch is lost if the app is killed or suspended before it reports.

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
    capabilities = frozenset({"read_matches", "read_messages", "send"})

    def read_matches(self, token: str) -> list[dict]: ...
    def read_messages(self, token: str, match_id: str) -> list[dict]: ...
    def send(self, token: str, match_id: str, text: str) -> dict: ...  # the sent message: `id`, `sent_at`
```

Never call a connector method directly. Go through `call()`, which reads the user's token from the vault, passes it to the method and enforces the rules below:

```python
matches = call(db, user_id, TinderConnector(), "read_matches")
messages = call(db, user_id, TinderConnector(), "read_messages", match_id)
```

- **Switch a capability off:** set `CONNECTOR_DISABLED_CAPABILITIES=tinder:send,hinge:like` (comma-separated `app:capability`).
- **Unavailable:** `unavailable(db, user_id, connector, capability)` returns the reason, or `None`. `call()` raises `CapabilityUnavailable` and does not touch the app when the capability is not declared, is disabled, the app is copilot-only, or the user has no stored token for the app.
- **Fallback to copilot:** if the connector method raises, `call()` inserts a row in `connector_alerts` (`user_id`, `app`, `capability`, `error` = `repr()` of the exception) and raises `CapabilityFailed`, with the connector's exception as `__cause__`. The row is written in its own transaction, so it survives the failed job's rollback. That row is both the alert and the fallback: `is_copilot_only(db, user_id, app)` is true while the user has any alert for the app, and every capability of that app is then unavailable for that user. `alerts(db, user_id)` lists them. Delete the user's rows for an app to re-enable its connector.
- **Ban detection:** `classify(error)` sorts the connector's exception into `auth failure` (HTTP 401), `ban signal` (HTTP 403) or `transient` (anything else), stored in the alert's `reason`. An auth failure or ban signal also calls `pause(user_id, app, reason)` in the same transaction as the alert, so that app's autopilot stops for that user; a transient error does not pause. `GET /connectors/alerts` returns the user's alerts (`id`, `app`, `capability`, `reason`, `error`, `created_at`), newest first. A fresh token lifts the copilot-only fallback but not the pause: resume with `POST /autopilot/resume?app=...`.

Test a connector's callers with a fake like `FakeConnector` in `tests/test_connectors.py`.

## Push notifications

All in `app/push.py`. To notify a user, call one function from a route or a job handler:

```python
from app.push import send_push

send_push(db, user_id, "Hot lead", "Ada replied", card_id=card_id)
```

- The push goes to every device the user registered. With `card_id`, tapping it opens that card in the app; without, it opens the app.
- It is best effort and never raises for an APNs failure: a refusal or a network error is logged as a warning.
- The iOS app registers its device with `POST /devices` and body `{"token": "<APNs device token in hex>"}`. A token belongs to the user who registered it last. When Apple answers `410` or `BadDeviceToken` for a token, its row in `devices` is deleted.
- Settings, passed by Compose to the API and worker. While any of the first four is unset, `send_push()` sends nothing and logs one line at `INFO`.

| Variable | Value |
| --- | --- |
| `APNS_KEY` | The contents of the `.p8` key from the Apple developer account. Line breaks may be written as `\n`. |
| `APNS_KEY_ID` | The key's 10-character ID |
| `APNS_TEAM_ID` | The developer team ID |
| `APNS_BUNDLE_ID` | The app's bundle identifier, `com.datingcrm.app` unless you changed it |
| `APNS_SANDBOX` | Set to `1` when the app is run from Xcode. Leave unset for TestFlight and App Store builds. |

- Tests never reach Apple: the autouse `apns` fixture replaces `post()`, the only function that calls APNs, and sets throwaway settings. Read `apns.sent` (each has `url`, `headers`, `payload`) to see what was pushed, and set `apns.answers["<token>"] = (410, "Unregistered")` to choose Apple's answer for a device.
- Sending to the real APNs has not been tried: no Apple developer account was available when this was written.

## Google Calendar holds

All in `app/calendar.py`; the table is `calendar_holds` (one row per slot held or confirmed for a match).

### What the owner sets up in Google Cloud

Do this once per server, at <https://console.cloud.google.com>:

1. Create a project.
2. In APIs & Services > Library, enable the **Google Calendar API**.
3. In APIs & Services > OAuth consent screen, choose user type **External**, and add the scopes `.../auth/calendar.events` and `.../auth/calendar.freebusy`. Add your own Google account under Test users.
4. Set the publishing status to **In production**. In **Testing**, Google expires the refresh token after 7 days and the calendar disconnects. Your own unverified app shows a warning page on connect; continue through it.
5. In APIs & Services > Credentials, create an **OAuth client ID** of type **Web application**. Add `https://<your server>/calendar/callback` as an authorized redirect URI (`http://localhost:8000/calendar/callback` for local use).
6. Give the server the three values. Compose passes them to the API and worker:

| Variable | Value |
| --- | --- |
| `GOOGLE_CLIENT_ID` | The OAuth client's ID |
| `GOOGLE_CLIENT_SECRET` | The OAuth client's secret |
| `GOOGLE_REDIRECT_URI` | The redirect URI from step 5, character for character |

### Connect

| Route | Does |
| --- | --- |
| `GET /calendar/connect` | Returns `{"url": "..."}`: Google's consent page. Open it in a browser. `503` while a variable above is unset. |
| `GET /calendar/callback?code=&state=` | Where Google sends the browser. Stores the refresh token and shows one line of text. It takes no API token: `state` names the user and is valid for 10 minutes. |
| `GET /calendar` | `{"connected": true}` once a refresh token is stored. |

The refresh token is stored in the token vault under the app name `google_calendar`. Never log it. Only the user's primary calendar is used. To disconnect, remove the app's access at <https://myaccount.google.com/permissions>; there is no disconnect route.

### Functions for the chat autopilot

All take the caller's transaction as `db`. Datetimes must be timezone-aware.

```python
from app import calendar

slots = calendar.free_slots(db, user_id, start, end, duration=timedelta(hours=2))  # [(start, end), ...]
hold_id = calendar.hold_slot(db, user_id, card_id, start, end, trigger="chat autopilot: proposed a time")
calendar.release_holds(db, user_id, card_id, trigger="match declined")
calendar.confirm_date(db, user_id, card_id, trigger="match agreed", start=start)  # True if a hold was confirmed
```

- `free_slots()` cuts the window into slots of `duration` from `start` and returns those that touch no busy time in Google and no row in `calendar_holds`. Choosing the window (which days and hours) is the caller's job.
- `hold_slot()` must be called for every slot a message offers. It creates a tentative event named "Hold: date with <name>". It raises `SlotTaken` if the slot is busy in Google or overlaps any slot held or confirmed for a match.
- Two matches never get the same slot because the database refuses it: `calendar_holds` has an exclusion constraint, so no two rows of one user overlap. A second hold on an overlapping slot fails even if two jobs race.
- `release_holds()` deletes the card's tentative events and their rows. Call it when the match declines. `PATCH /cards/{id}` with `stage: archived` calls it too.
- `confirm_date()` turns the hold that starts at `start` into a confirmed event named "Date with <name>" and releases the card's other holds. Without `start` it confirms only if the card has exactly one hold. `PATCH /cards/{id}` with `stage: date_set` calls it without `start`, so a card with several holds keeps them until code names the agreed slot.
- Code that sets a card's stage without the `PATCH` route must call `calendar.stage_changed(db, user_id, card_id, stage)`.
- A confirmed row stays and keeps its slot taken. Archiving the card later does not delete the event.
- Every hold, release and confirmation writes a `calendar_hold` entry to the audit log with target `card:<id> hold|release|confirm <start in UTC>` and the given trigger.
- All four raise `NotConnected` if the user has no stored refresh token, and `httpx.HTTPError` if Google refuses or cannot be reached; nothing is stored then. The `PATCH` route answers `502` and leaves the stage unchanged.
- Tests never reach Google: the autouse `gcal` fixture replaces `calendar.google`, the only object that calls Google. Set `gcal.busy` to `(start, end)` pairs and read `gcal.events`.
- Calls to the real Google API have not been tried: no Google credentials were available when this was written. Check the scopes, the free/busy response and the event fields in `GoogleCalendar` on the first real connect.

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

`app/tinder.py` reads your own Tinder account with your own web session token. It supports `read_matches`, `read_messages` and `send`. Nothing sends on its own: a message goes out only when the user taps send on a draft (see "Drafts"). Set `CONNECTOR_DISABLED_CAPABILITIES=tinder:send` to keep it read-only. Tinder's terms do not allow this API use; see Risks in the spec.

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
| `POST https://api.gotinder.com/user/matches/{match_id}` with the JSON body `{"message": "<text>"}` sends a message (no `/v2` prefix, no other body field such as a temporary message ID) | `send` |
| That request answers `200` with the sent message as the whole body (not wrapped in `data`), with `_id` and `sent_date` as in a read message | Message `external_id` and time. If `_id` differs from the ID a later read gives, sync adds the message a second time |
| Any answer other than `2xx` means the message may or may not have been sent | A failed send is never retried |
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
