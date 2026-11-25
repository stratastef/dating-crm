# Match read

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
- `_allowed()` checks every inference Claude replies before it is stored, and drops it when: a field is missing, the evidence is empty or the confidence is outside 0 to 1; it is about anyone but the match (`about` is not `match`); it targets an insecurity; its kind is not listed above; or it guesses a protected trait (ethnicity, religion, health, sexuality, politics) and the user has not opted in. The `about`, `protected_trait` and `targets_insecurity` labels are Claude's own, so `_allowed()` also asks Jev about the inference's text (`jev.read_hits()`), whatever the labels say. `about_other_person` or `targets_insecurity` drops it. `guesses_protected_trait` drops it unless the user opted in; then it is stored as protected (`unlabelled` if Claude gave no trait), so opting out hides it. When Jev cannot be asked the inference is dropped, so a read stores nothing until Jev is configured.
- With the opt-in on, a protected trait may also be its own kind (`religion` and so on). Opting out hides stored protected-trait inferences from the read and from drafts; it does not delete them.
- With no photos on the card the read is from text only.
- Other server code reads the card's read with `read_lines(db, user_id, card_id)`.
- The read route returns `502` if Claude's reply is not a JSON list; the last read is kept.
