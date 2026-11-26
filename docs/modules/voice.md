# Voice

Routes and the job are in `app/voice.py`; the table is `voice_profiles` (one row per user).

| Route | Does |
| --- | --- |
| `PUT /voice/questionnaire` | Replace the questionnaire answers. Body: `{"answers": {"<question>": "<answer>"}}`. Returns the same shape as `GET /voice`. |
| `GET /voice` | Read `questions`, `answers` and `profile`. `profile` is `null` until the worker has written it. |
| `GET /cards/{id}/similar-chats?limit=` | Past chats that led to a date, most similar to this card's conversation first. `limit` defaults to 3. |

- **The voice questionnaire** is `QUESTIONS` in `app/voice.py`, served as `questions` so the app renders them; edit them there. Answers are keyed by the question's exact text, so a reworded question starts unanswered and its old answer stays under the old text. The app sends no answer for a question left blank.
- The `voice_profile` job writes the style profile from the answers and the user's own messages (the newest 200). Saving answers and `POST /cards/{id}/messages` with `sender: me` queue it. Every message is stored by `insert_message()` (see "Cards and messages"), which queues it.
- A chat led to a date if its card has `led_to_date: true`. A trigger on `cards` sets the label when the stage is `date_set`, `dated` or `seeing_them` or the date is rated, and nothing unsets it, so an archived card keeps it.
- A chat that led to a good date (`is_good_date()`) ranks as if it were `GOOD_DATE_BOOST` (1.5) times as similar. Each result carries its `date_rating`.
- The job also reads the newest 20 draft edits (`original` against `edited`), and `PATCH /drafts/{id}` queues it. See "Feedback loop".
- Similarity is `similarity()` from the Postgres `pg_trgm` extension over the whole chat text, so it measures shared wording, not meaning. Other code calls `similar_chats(db, user_id, card_id, limit)`.
