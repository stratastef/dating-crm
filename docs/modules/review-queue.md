# Review queue

All in `app/review.py`. A pending draft waits in the queue until the user approves or dismisses it; editing is `PATCH /drafts/{id}`.

| Route | Does |
| --- | --- |
| `GET /queue` | List what waits for the user, hot leads first, then oldest first. |
| `POST /drafts/{id}/approve` | Set the draft's `status` to `approved` and return it. `409` if it is no longer pending. |
| `POST /drafts/{id}/dismiss` | Set the draft's `status` to `dismissed` and return it. Releases the calendar holds of the slots the draft offered. `409` if it is no longer pending, `502` if Google could not be reached (the draft stays pending). |

- A queue item is `{"kind", "hot", "card_id", "card_name", "card", "draft", "message", "triggers", "suggestions", "paid_item"}`. Each item carries what the user needs to decide without opening the chat:
  - every item of a card: `card` is its card summary (`Card` in `app/cards.py`: name, lead photo, dating app and the rest; see "Cards and messages");
  - kind `draft`: `draft` holds the draft, whose `kind` is `opener` or `reply`. For a reply, `message` is the message it answers, `{"body", "sent_at"}`: the newest message from the match sent before the draft was written. An opener has none;
  - kind `handover` (a card whose handover is pending, see "Handover"): `triggers` are the handover checks that fired (`asks_if_ai`, `logistics`, `place_or_exclusivity`, `personal_info`, `sensitive`, or `unavailable` when Jev could not be asked), and `message` is the message that fired them: the newest message from the match with a stored hit. `suggestions` holds the suggested replies. Both are null when no hit is stored;
  - kind `paid_item` (see "Paid items"): `paid_item` holds the proposal, with the candidate's `photo_url`, its `candidate_id` (the app opens the profile from it) and the `cost` the connector reported. `card` and `card_id` are null and `card_name` is the proposal's `name`. It is never hot.
- **Order:** hot leads first, then oldest first across kinds. A draft's age is when it was written, a paid item's when it was proposed, and a handover's the time of the message that fired it (`shortcut:` in `queue()`: the card does not store when its handover began).
- **A new kind of item** (`copied_draft`, `failed_send`) adds its own `kind`, a loop in `queue()` that appends `(time it began to wait, QueueItem)`, and any field it needs on `QueueItem`. The sort does the rest.
- `is_hot_lead(db, user_id, card_id)` is the only definition of a hot lead: the match sent a message within the last hour, Jev's hot-lead triage flagged a pending draft of the card (`drafts.hot_lead`), the card's handover is pending, or a date is being coordinated (a slot is held for the match, or a message of theirs that hit `logistics` is unanswered). An item's `hot` is its card summary's `hot`.
- `POST /cards/{id}/drafts` calls `notify_if_hot()`, which sends one push at once for a hot lead and nothing otherwise. Call it wherever else an item joins the queue.
- Approving sends the draft when its card's app can send: `hand_on_approved_draft(db, user_id, draft)` is called once per approved draft and queues the `send_draft` job (see "Drafts"). When the app cannot send (no connector, `send` unavailable, card without `external_id`), the approval still succeeds, the draft stays `approved` and the user copies it.
- Undo of a dismissal is the app's: Review holds the `dismiss` call for the 5 seconds its Undo toast shows (see "iOS app shell", "Review"). The server has no undo route.
