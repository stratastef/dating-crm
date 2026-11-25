# Handover

All in `app/handover.py`. When a new message from the match hits the handover trigger (`messages.handover` is not empty, see "Jev checks"), autopilot is paused for that card only and the user gets a push with suggested replies.

| Route | Does |
| --- | --- |
| `POST /cards/{id}/take-over` | Keep the chat manual until `hand-back`. Returns `{"handover", "handover_suggestions"}`. |
| `POST /cards/{id}/hand-back` | End the pause, pending or taken over. Returns the same two fields. |

- A card has `handover` and `handover_suggestions`. `handover` is null (autopilot may chat), `pending` (a trigger hit and the user has not answered) or `taken_over`. A new message from `me` ends `pending`; only `hand-back` ends `taken_over`.
- Before autopilot sends to a card, it must call `handover.is_paused(db, user_id, card_id)` and send nothing when it is true. This is next to `autopilot_allowed()`, which knows apps and jobs but not cards.
- `insert_message()` calls `handover.incoming()` for a message from `them` and `handover.answered()` for one from `me` (see "Cards and messages").
- Suggested replies: one Claude call (purpose `handover`) writes up to three. Each goes through `jev.guardrail_hits()` and is dropped on any hit. Each is also judged together with the match's unanswered messages (`jev.answer_denies_ai(db, user_id, question, answer)`), so a bare "Nope" to "are you a bot?" is dropped too and no suggestion denies being AI. There are none when Jev is unavailable, the AI budget is reached or Claude fails; the card is paused and the push is sent all the same.
- The push goes through `notify_if_hot()`; a pending handover is a hot lead. Its body is the suggestions, one per line.
- A hit on any message the user has not answered pauses the card, newest or not: an app may deliver a batch newest first. A hit on a message with a later message from `me` does nothing. Chat autopilot reads the hits of every unanswered message the same way (`unanswered()` in `app/card_lookup.py`). A message that is already answered, or older than a day, is not sent to Jev at all, so a first sync of old chats costs nothing, pauses nothing and sends nothing. Chat autopilot does not send alone while such an unchecked message is unanswered (see "Chat autopilot"). A hit on a card that is already paused changes nothing.
