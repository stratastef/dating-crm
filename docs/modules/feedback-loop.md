# Feedback loop

Nothing is trained in v1. What the user did changes later prompts and retrieval only. `app/feedback.py` holds the swipe part and the export.

| Signal | Changes |
| --- | --- |
| Chat outcome: `led_to_date` and `date_rating` on the card | `similar_chats()` returns only chats that led to a date, good dates first. |
| Draft edit: `edited` differs from `original` | The `voice_profile` job reads the newest 20 edits under `<my_edits>`; an edit queues the job. |
| Manual swipe against the suggestion | The pre-screen prompt lists the newest 10 under `<manual_swipes>` (bio, suggestion, decision). Unattended swipes and swipes that agree with the screen are left out. |
| Date rating | The pre-screen prompt lists the newest 10 rated dates under `<rated_dates>`: the rating with the card's `notes` and `date_note`. |

- `GET /feedback/export` returns the caller's labelled data as JSON Lines (`application/x-ndjson`), one example per line, for later fine-tuning. `type` is `chat` (`app`, `led_to_date`, `date_rating`, `good_date`, `messages`), `draft_edit` (`kind`, `original`, `edited`) or `swipe` (`app`, `bio`, `suggestion`, `decision`; manual swipes only). No names or IDs.
- The export is read from the live tables at each request and stored nowhere, so a purged person is not in it. A table that stores feedback must reference `cards` or `swipe_candidates` with ON DELETE CASCADE.
