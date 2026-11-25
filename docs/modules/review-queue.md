# Review queue

All in `app/review.py`. A pending draft waits in the queue until the user approves or dismisses it; editing is `PATCH /drafts/{id}`.

| Route | Does |
| --- | --- |
| `GET /queue` | List what waits for the user, hot leads first, then oldest first. |
| `POST /drafts/{id}/approve` | Set the draft's `status` to `approved` and return it. `409` if it is no longer pending. |
| `POST /drafts/{id}/dismiss` | Set the draft's `status` to `dismissed` and return it. Releases the calendar holds of the slots the draft offered. `409` if it is no longer pending, `502` if Google could not be reached (the draft stays pending). |

- A queue item is `{"kind", "hot", "card_id", "card_name", "draft", "suggestions"}`. For kind `draft`, `draft` holds the draft. For kind `handover` (a card whose handover is pending, see "Handover"), `suggestions` holds the suggested replies and `draft` is null. For kind `paid_item` (see "Paid items"), `paid_item` holds the proposal, `card_id` is null and `card_name` is the proposal's `name`; it is never hot. A new kind of item adds its own `kind`.
- `is_hot_lead(db, user_id, card_id)` is the only definition of a hot lead: the match sent a message within the last hour, Jev's hot-lead triage flagged a pending draft of the card (`drafts.hot_lead`), the card's handover is pending, or a date is being coordinated (a slot is held for the match, or a message of theirs that hit `logistics` is unanswered).
- `POST /cards/{id}/drafts` calls `notify_if_hot()`, which sends one push at once for a hot lead and nothing otherwise. Call it wherever else an item joins the queue.
- Approving sends the draft when its card's app can send: `hand_on_approved_draft(db, user_id, draft)` is called once per approved draft and queues the `send_draft` job (see "Drafts"). When the app cannot send (no connector, `send` unavailable, card without `external_id`), the approval still succeeds, the draft stays `approved` and the user copies it.
