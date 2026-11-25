# Swipe copilot

All in `app/swipes.py`; the table is `swipe_candidates` (one row per profile an app offered). The app suggests like or pass and the user decides every one: nothing is swiped until they do. It works for every connector in `CONNECTORS` that has `read_candidates`, `like` and `pass`.

| Route | Does |
| --- | --- |
| `POST /swipes/{app}/suggestions` | Read the app's next candidates, suggest for each new one, and return all that wait. `409` when the connector is unavailable (no token, copilot-only, switched off), `502` when the app fails, `404` for an app with no connector. |
| `GET /swipes?app=` | The candidates that wait for the user's swipe, oldest first. Calls neither the app nor Claude. |
| `POST /swipes/{id}/decision` with `{"decision": "like"}` | Store the user's swipe (`like` or `pass`), then swipe in the app. `409` if already swiped. |

- A candidate is `{"id", "app", "name", "bio", "photos", "suggestion", "reason", "source", "decision"}`. `photos` are URLs for the user to look at. `source` is the pre-filter that suggested: `jev` or `model`.
- **Pre-filters, cheapest first:** `jev.dealbreaker_hit()` asks Jev about each bio sentence and each of the user's dealbreakers; a hit is a `pass` with no Claude call. The rest go to a cheap Claude model through `llm.call()` with purpose `swipe_prescreen`. The model is read from `SWIPE_PRESCREEN_MODEL` (default `claude-haiku-5-5`). It sees the preferences in force, the name and the bio. Photos are never analysed.
- One request screens at most `BATCH` (10) new profiles, inside the request. A profile already stored is not screened again. At the AI budget the request stops screening and returns what it has; Jev is under the same budget, so nothing new is screened then. A model answer that is neither `like` nor `pass` stores nothing; the profile is screened again when the app offers it next.
- **Manual swipes:** a decided row is kept with both `suggestion` and `decision`. These rows are the manual-swipe preference signal: the pre-screen prompt holds `feedback.swipe_lines()` (see "Feedback loop").
- The decision route answers with the candidate plus `applied`. `applied: false` means the app was not reached (connector unavailable or failed, see "Connectors"): the swipe is stored and the user swipes in the dating app by hand.
- `apply_decision(db, user_id, app, profile_id, decision)` is the one function that swipes through a connector. Swipe autopilot must call it and `record_action()`. It sends a plain like or pass and never spends a paid item.
- The copilot routes do not read the swipe autonomy level: a request from the user is the consent.
- Find and purge: a candidate is not a card. Find it with `GET /people/candidates` and purge it with `candidate_ids` (see "Find and purge"). The dating app may offer a purged profile again; it is not stored again.
