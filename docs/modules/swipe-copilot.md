# Swipe copilot

All in `app/swipes.py`; the table is `swipe_candidates` (one row per profile an app offered). The app suggests like or pass and the user decides every one: nothing is swiped until they do. It works for every connector in `CONNECTORS` that has `read_candidates`, `like` and `pass`.

| Route | Does |
| --- | --- |
| `POST /swipes/{app}/suggestions` | Read the app's next candidates, suggest for each new one, and return all that wait. `409` when the connector is unavailable (no token, copilot-only, switched off), `502` when the app fails, `404` for an app with no connector. |
| `GET /swipes?app=` | The candidates that wait for the user's swipe, oldest first. Calls neither the app nor Claude. |
| `POST /swipes/{id}/decision` with `{"decision": "like"}` | Store the user's swipe (`like` or `pass`), then swipe in the app. `409` if already swiped. |
| `GET /swipes/layout` | The user's Swipe layout: `{"layout": "one_at_a_time"}`, `"list"`, or `null` until they choose. |
| `PUT /swipes/layout` with `{"layout": "list"}` | Choose the Swipe layout. Only the two values; `422` for anything else, `null` included. |

- A candidate is `{"id", "app", "name", "bio", "photos", "age", "distance_mi", "suggestion", "reason", "source", "decision", "paid_item"}`. `photos` are URLs for the user to look at. `age` and `distance_mi` are `null` when the dating app does not say (a connector's `read_candidates` may add them). `source` is the pre-filter that suggested: `jev` or `model`. `paid_item` is the Super Like proposed for the profile, shaped as in "Paid items", while it waits; `null` otherwise.
- **Swipe layout** (ADR 0004): `users.swipe_layout`, null until the user chooses. The app shows one at a time meanwhile. The setup step counts it as chosen once it is not null.
- **Pre-filters, cheapest first:** `jev.dealbreaker_hit()` asks Jev about each bio sentence and each of the user's dealbreakers; a hit is a `pass` with no Claude call. The rest go to a cheap Claude model through `llm.call()` with purpose `swipe_prescreen`. The model is read from `SWIPE_PRESCREEN_MODEL` (default `claude-haiku-5-5`). It sees the preferences in force, the name and the bio. Photos are never analysed.
- One request screens at most `BATCH` (10) new profiles, inside the request. A profile already stored is not screened again. At the AI budget the request stops screening and returns what it has; Jev is under the same budget, so nothing new is screened then. A model answer that is neither `like` nor `pass` stores nothing; the profile is screened again when the app offers it next.
- **Manual swipes:** a decided row is kept with both `suggestion` and `decision`. These rows are the manual-swipe preference signal: the pre-screen prompt holds `feedback.swipe_lines()` (see "Feedback loop").
- The decision route answers with the candidate plus `applied`. `applied: false` means the app was not reached (connector unavailable or failed, see "Connectors"): the swipe is stored and the user swipes in the dating app by hand.
- `apply_decision(db, user_id, app, profile_id, decision)` is the one function that swipes through a connector. Swipe autopilot must call it and `record_action()`. It sends a plain like or pass and never spends a paid item.
- The copilot routes do not read the swipe autonomy level: a request from the user is the consent.
- Find and purge: a candidate is not a card. Find it with `GET /people/candidates` and purge it with `candidate_ids` (see "Find and purge"). The dating app may offer a purged profile again; it is not stored again.

## On the phone

`SwipeView` (`ios/DatingCRM/Screens/SwipeView.swift`) is the Swipe tab. It reads the swipe autonomy level, the Swipe layout and the candidates each time the tab appears.

- **Off:** with swipe autonomy Off (the default), the tab explains Copilot and Autopilot and links to `AutopilotView`.
- **One at a time** (also while the layout is null): "1 of 4", the photos as pages under a glass plate with name, age, distance and app; a tap opens a photo full screen. Then the AI suggests line with its reason, the proposed Super Like with Not now and Super Like (approve and decline, see "Paid items"), and the bio. Pass and Like sit in a bar above the tab bar; the suggested one is filled. No drag gesture.
- **List:** "Accept all suggestions", then a row per candidate with the face, the suggestion and its reason, and Pass and Like with the suggestion filled. A proposed Super Like is only named; it is answered in Review or one at a time.
- **Undo:** Pass, Like and Accept all take the candidates off the screen and show a toast with Undo. The app sends the swipes only when the 5 seconds are over (`Held`, `Components/Held.swift`), so Undo leaves nothing on the server or the dating app. A swipe that waits is not shown again by a reload. Closing the app in those 5 seconds drops the swipe: the candidate still waits.
- **Swipe layout under You:** You > Swipe layout shows `SwipeLayoutSection(client:)` (`Components/SwipeLayoutSection.swift`), one list section that loads and saves the setting itself.
