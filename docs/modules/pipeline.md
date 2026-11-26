# Pipeline

All in `app/pipeline.py`. The Pipeline groups every card by who acts next, not by stage (ADR 0007). The server decides the group and the reason; the app renders them and keeps the copy, keyed on these codes.

| Route | Does |
| --- | --- |
| `GET /pipeline` | Every card of the user as `[{"group", "cards"}]`: the groups in order, empty ones left out. Each card is a card summary (see "Cards and messages"). Inside a group, hot leads first, then the most recent activity: the last message, or the last stage change when there are no messages. |

## Grouping

`place(db, user_id, summaries)` sets each card summary's `pipeline_group`, `reason`, `handover_trigger` and `autopilot_activity`. `summarize()` in `app/cards.py` calls it, so every card response carries them, not only `GET /pipeline`.

An Archived card is `archived`, whatever else is true of it: archiving is how the user is done with a card (as in the prototype). Every other card gets the first group that matches:

1. **`waiting_for_you`**, when a reason applies. The first that applies, in this order, is `reason`:
   1. `handover`: the handover is pending. `handover_trigger` is the first check the newest flagged message from the match hit (`logistics`, `asks_if_ai`, `place_or_exclusivity`, `personal_info`, `sensitive`, or `unavailable` when Jev could not be asked); null for every other reason.
   2. `draft_in_review`: a draft is pending.
   3. `copied_draft`: a draft of the card is `copied` and its message has not appeared in the chat yet (see "Drafts").
   4. `failed_send`: a draft of the card is `failed`.
   5. `stalled`: the card is Stalled.
   6. `overdue`: the card has a next action and its due day is before today. Due today is not overdue. Today is the user's day in their time zone (`user_zone()`), as on Today.
   7. `rate_date`: a Dated card has no rating.
   8. `your_turn`: a Matched or Chatting card autopilot is not handling, whose last message is from the match.
   9. `opener_due`: a Matched card autopilot is not handling, with no messages.
2. **`handled_by_autopilot`**: a Matched or Chatting card autopilot is handling (below). `autopilot_activity` is `drafting_reply` (the match wrote last and a `chat_reply` job is queued or running) or `sent_waiting` (the user or autopilot wrote last). The time to show is `last_message.sent_at`, and the row ends with the card's `topic` (see "Cards and messages").
3. **`waiting_for_them`**: every other Matched or Chatting card.
4. **`texting_off_app`**: Number swapped, Date set, Dated and Seeing them.

**Handled by autopilot** needs all of these:

- chat autopilot may act for the card's app: nothing is paused for it or for all apps, the AI budget is not reached, and chat autonomy is Autopilot or Full autopilot (`autopilot_block()`);
- the app can send to the card: it has a working connector (not copilot-only, a session token stored, `send` not switched off) and the card is linked to a match (`refusal()` in `app/send.py`, the rules an unattended send is held to);
- the card has no handover, pending or taken over;
- autopilot is doing something: the user or autopilot wrote last, or the match wrote last and a `chat_reply` job is queued. A reply job that wrote nothing (no style profile, an old message) leaves the card `your_turn`.

Autopilot sends no openers yet, so a new match is `opener_due` even when autopilot may act. When #73 adds the opener job, a card with no messages and that job queued becomes Handled by autopilot with `autopilot_activity` `writing_opener`.

## Adding a reason or an activity

- A reason: add it to `Reason` in its precedence slot and add its check to `_reason()` at the same place. Fetch what it needs in `place()` with one query over all the cards (`card_id = ANY(:ids)`), like `failed`.
- An activity: add it to `Activity` and set it in the `handled_by_autopilot` branch of `place()`.
- The app words each code in `Card.pipelineStatus` (`ios/DatingCRM/Screens/PipelineView.swift`); a code it does not know shows no status line.
