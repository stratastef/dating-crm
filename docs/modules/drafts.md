# Drafts

Routes are in `app/drafts.py`; the table is `drafts` (one row per draft).

| Route | Does |
| --- | --- |
| `POST /cards/{id}/drafts` | Have Claude write a draft for the card and store it. `kind` is `opener` when the card has no messages, else `reply`. |
| `PATCH /drafts/{id}` | Store the user's edit. Body: `{"edited": "..."}`. |
| `POST /drafts/{id}/send` | The user approves the draft: queue it for the worker to send. Returns `202` and the draft. In `app/send.py`. |

- A draft is `{"id", "card_id", "kind", "status", "original", "edited"}`. `original` is Claude's text and never changes; `edited` is `null` until the user edits. The text to use is `edited` if set, else `original`.
- `status` is `pending` until the user sends, approves or dismisses the draft (see "Review queue"). A sent or approved draft is `approved` (queued), then `sending` (the worker is sending it) and `sent` or `failed`. A dismissed draft is `dismissed`. The user can still copy any draft.
- **Send:** the route answers `409` with the reason and queues nothing when the draft is not `pending`, the app has no connector, the card has no `external_id`, or `send` is unavailable (see "Connectors": not declared, switched off, copilot-only, no token).
- **Queue a send from code:** `queue_send(db, user_id, draft_id, trigger)` in `app/send.py` is the one way to send a draft. It moves a `pending` draft to `approved` and queues a `send_draft` job in your transaction; it returns the draft, or `None` if the draft is not `pending`. `trigger` goes to the audit log. A tap is not held by the kill switch or the autonomy level: both stop autopilot only, so the user can always send a draft they have read. A send no user asked for must pass `unattended=True`: see "Chat autopilot".
- **Guardrail and the tap:** the user's tap or approval sends a draft with a guardrail hit, because the guardrail's job is to put the draft in front of them. The one exception is `denies_ai`: such a draft is never sent, by a tap (`409`), an approval (it stays `approved`) or the job, until the user edits it and the guardrail runs again. The review queue approves the draft itself, so it calls `send_approved(db, user_id, draft_id, trigger)`, which queues the job for an already `approved` draft if the app can send.
- **The `send_draft` job** sends the text (`edited` if set, else `original`) with the connector's `send`, stores the message on the card under the app's message ID (so sync does not add it twice), writes an audit log entry (`type: message`, `target: card:<id>`) and sets `sent`. If `send` became unavailable after the tap, nothing is sent and the draft goes back to `pending`.
- **At most once:** the job commits `sending` before it calls the app. If the app answers with an error, or the worker dies before the job commits, the draft ends as `failed` and is never sent again, because the message may have gone out. A `failed` draft whose message did go out appears on the card at the next sync. To try again, write another draft.
- The prompt holds the style profile, the card's app, name and notes, the match read (its `tone` sets the draft's tone), the conversation, and `similar_chats()` as examples.
- **Offering a time:** every draft that offers a slot holds it, in every autonomy mode. When the match's unanswered messages hit `logistics`, no slot is held for the card yet and the calendar is connected, `draft_for()` tells Claude to name no day or time and adds the sentence from `calendar.offer_slots()`, which holds each slot it names for that draft. Without a connected calendar the draft offers nothing by itself; a time Claude or the user writes into the text is not held. `POST /drafts/{id}/dismiss` and a failed send release the draft's holds.
- The write route returns `409` until the style profile is written, and `502` if Claude's reply is empty. Other code calls `draft_for(db, user_id, card_id)`, which raises `CannotDraft` in those cases (its `status` is the route's answer); a job catches it and never sees an `HTTPException`.
- A draft also has `guardrail` and `hot_lead`, the results of its Jev checks (see below).
