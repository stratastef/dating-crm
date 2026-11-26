# Cards and messages

A card is one match. Routes are in `app/cards.py`; tables are `cards` and `messages`. All routes need a token and see only the caller's rows; a card that is not yours is `404`.

| Route | Does |
| --- | --- |
| `POST /cards` | Create a card. Body: `app`, `name`, optional `external_id`, `stage` (default `matched`), `notes`, `next_action`, `due_date`. |
| `GET /cards?stage=&app=` | List cards, oldest first. Both filters are optional. |
| `GET /cards/{id}` | Read one card. |
| `PATCH /cards/{id}` | Change only the fields sent: `name`, `stage`, `notes`, `next_action`, `due_date`. `null` clears `next_action` or `due_date`. |
| `POST /cards/{id}/messages` | Add a message. Body: `sender` (`me` or `them`), `body`, optional `sent_at` (default now), `external_id`. |
| `GET /cards/{id}/messages` | List the card's messages by `sent_at`. |

- **A message** is `{"id", "card_id", "external_id", "sender", "body", "sent_at", "handover", "sent_by_autopilot"}`. `handover` is the handover checks a message from the match hit (null when not checked). `sent_by_autopilot` is true for a message autopilot sent alone, so the chat marks it with the Autopilot marker; it is false for the user's own messages, drafts they sent included. The `send_draft` job sets it for an unattended send (see "Drafts"). Messages stored before migration `t59_sent_by_autopilot` are all false.

- **Card summary.** Every card the API returns (these routes, `GET /people`, and later list routes) carries what a row in the app shows, so the app makes no other call:
  - `stalled` and `stage_changed_at` (below);
  - `last_message`: the newest message by `sent_at`, whoever sent it, as `{"sender", "body", "sent_at"}` with the first 100 characters of the body; null when the card has no messages;
  - `hot`: `is_hot_lead()` (see "Review queue"), the same answer the review queue gives;
  - `pending_draft`: the newest pending draft, as the review queue shows it, with `sendable`; null when there is none;
  - `drafts`: the card's draft list, its `pending`, `copied` and `failed` drafts, newest first, so the card can dock them (ADR 0003). Sent, queued and dismissed drafts are not in it;
  - `lead_photo_url`: the first photo attached with `POST /cards/{id}/photos`; null when unknown;
  - `pipeline_group`, `reason`, `handover_trigger` and `autopilot_activity`: where the Pipeline lists the card and why (see "Pipeline");
  - `topic`: what the chat is about in a few words, such as `museums`. The call that writes a draft gives it (see "Drafts") and it is stored on the card (`cards.topic`); a later draft replaces it. Empty until the card's first draft.

  `summarize(db, user_id, rows)` in `app/cards.py` builds it from card rows selected with `_COLUMNS`, keeping their order. A route that returns cards selects the rows and returns `summarize(...)`; a new summary field is added there and to `Card`.
- `stage` is one of `matched`, `chatting`, `number_swapped`, `date_set`, `dated`, `seeing_them`, `archived`. Anything else is `422`. `stage_changed_at` on the card is the time of the last stage change; there is no stage history table.
- Stalled is a flag on the card, not a stage. The hourly `mark_stalled` job sets `stalled: true` on a card in `chatting`, `number_swapped` or `date_set` whose last message, from either side, is older than the user's `stalled_after_days` (a card with no messages counts from `stage_changed_at`). A stalled card has `suggested_actions: ["revive", "archive"]`; otherwise the list is empty. A new message from `them` clears the flag, and so does moving the card out of those three stages; archive is `PATCH /cards/{id}` with `stage: archived`.
- `GET /settings` and `PATCH /settings` read and change the user's settings; `PATCH` changes only the fields sent. `stalled_after_days` is a whole number of days, at least 1, default 3. `time_zone` is the phone's time zone (see "Today"). `setup_dismissed` hides "Finish setup" on Today (see "Setup"). `push_name_previews` lets hot-lead and handover pushes name the match (see "Review queue"). `blur_photos` has the app blur faces until tapped; the server only stores it. Both are off by default.
- `PATCH /cards/{id}` also takes `date_rating` (1 to 5) and `date_note`, both null until the user rates the date. A rating needs no stage change, so a date synced into Dated gets rated too, and it counts on the dashboard from the first rating (`date_rated_at`). A good date is a rating of 4 or 5: `is_good_date()` in `app/cards.py` is the only definition, and the card's `good_date` field is its result. The card's `led_to_date` is the chat's outcome label (see "Voice").
- `app` is free text, for example `tinder` or `hinge`.
- `external_id` is the ID the dating app gives the match or message. It is unique per user and app for cards, and per card for messages; a duplicate is `409`. Rows without one are never duplicates.
- **Storing a message from other code:** `insert_message(db, user_id, card_id, external_id, sender, body, sent_at)` in `app/cards.py` is the one way to store a message. It runs everything a new message sets off: for `me`, the style profile is queued, a pending handover ends and the card's copied drafts older than the message become `sent`; for `them`, Stalled is cleared, the handover trigger runs and chat autopilot is asked to reply. The route and `upsert_message()` (which skips a message the card already has, and moves a Matched card to Chatting) both call it. Never insert into `messages` yourself.
- **Reading a card from other code:** use `app/card_lookup.py`, which every module can import. `own_card(db, user_id, card_id)` returns the user's card or raises `404` (for a route); `find_card()` returns `None` instead (for a job). `conversation()` is the card's messages as `(sender, body)`, oldest first, `chat_lines()` turns them into `sender: body` prompt lines, and `unanswered()` is the match's messages since the user's last one. Do not write these queries again.
