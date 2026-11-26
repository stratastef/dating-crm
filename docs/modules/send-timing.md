# Send timing

All in `app/timing.py` (ADR 0008). Every draft has a **send time** (`drafts.send_at`) and a one-line `timing_reason`. For autopilot it is when the **planned send** goes out; for the user's own drafts it is when the draft is best sent.

- **The formula:** `formula(db, user_id, card_id, now) -> timedelta`, the wait from `now`:
  - **pace:** the median of the match's last 5 reply gaps (from one of the user's messages to their answer), held to 1 minute–6 hours; 45 minutes when no gap is known;
  - times **engagement** of their messages since the user's last one: a question 0.75, 120 characters or more 0.8, under 20 characters with no question 1.25 (a question and length multiply);
  - times the **hour** of `now` in the user's time zone (`user_zone()`): 18:00–24:00 0.8, 09:00–18:00 1.2, otherwise 1;
  - counted from their last message, so the time since it is already waited (never below 0).
- **The model's adjustment:** `draft_for()` puts the formula's wait in the prompt (`<send_timing>`). Claude's `DraftReply` gives `adjustment` (a fraction of the wait: `-0.5` halves it, `0.5` adds half, default 0) and `timing_reason`, in the same call that writes the draft and the topic.
- **The hard bounds:** `send_time(db, user_id, card_id, wait, adjustment, now) -> datetime`, in this order:
  1. the adjustment is clamped to half either way (`MAX_ADJUSTMENT`);
  2. at least 2 minutes from `now` when the match is **live** (their last message is at most 5 minutes old), otherwise at least 10 minutes;
  3. at most 12 hours;
  4. never inside the user's **night window**: `outside_night(db, user_id, at)` moves a time inside it to the window's end plus 1–15 random minutes. It is last, so it wins over the 12-hour ceiling.
- **Night window setting:** `night_window_start` and `night_window_end` on `GET`/`PATCH /settings`: whole hours 0–23 in the user's time zone, 1 and 7 by default. A start after the end wraps past midnight (22 to 9); equal hours make no window. Other hours are `422`.
- **Planned sends:** the `chat_reply` job queues its reply with `queue_send(..., unattended=True, run_at=draft.send_at)`. The `send_draft` job asks `unattended_block()` again at that time, so a pause, the AI budget, a guardrail hit or a handover since then keeps the draft `pending`, in Review. The SQL condition for "this draft is a planned send" is `PLANNED` in `app/drafts.py`: `approved` with a queued, unattended `send_draft` job.
- **A new message from the match** (`insert_message()`) calls `drop_planned_sends()` in `app/send.py`: each planned send on the card is taken back with `cancel_send()`, `dismissed`, and its calendar holds are released. Chat autopilot then plans a new reply. One the worker is already sending goes out.
- **Where it shows:** the card summary's `planned_send` (a `Draft`, with `send_at` and `timing_reason`), and the Pipeline: a card with a planned send is Handled by autopilot with `autopilot_activity` `planned`.
- **For later tickets:** Send now and Hold (#72) act on `planned_send` with `cancel_send()`/`queue_send()`. Openers (#73) take their own random time and then `outside_night()`. Copilot suggested times (#74): every draft from `draft_for()` already has `send_at` and `timing_reason`.
- **Limits:** the weights are a first guess, not fitted to outcomes. The send time is planned when the draft is written: a copilot draft read hours later shows a time that has passed. Not run against the real Claude.
