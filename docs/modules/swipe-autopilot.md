# Swipe autopilot

The `swipe_autopilot` job in `app/swipes.py` likes and passes without the user. It is registered as `@handler("swipe_autopilot", autopilot="swipe", every=AUTOPILOT_INTERVAL)` (1 hour) and runs for every app in `CONNECTORS`.

- **Off by default.** The worker skips the job unless the user's swipe autonomy is `guardrails` or `full` (`PUT /autonomy/swipe`). The two levels act the same here.
- **What stops it:** `autopilot_allowed(db, user_id, app, "swipe")` is asked for each app and again before each swipe. So the kill switch (all apps or one), a ban or auth pause of the app and the AI budget cap all stop it, also in the middle of a run. A failed swipe ends the run for that app; after a transient error the next run tries again.
- **What it swipes:** the candidates that wait in `swipe_candidates`, oldest first, by their stored suggestion. It calls the copilot's `screen()` for new candidates only when fewer wait than it may swipe. It swipes with `apply_decision()`, so a paid item is never spent. A candidate with a pending paid-item proposal is skipped (see "Paid items").
- **Dealbreakers are checked again before each swipe**, with `jev.dealbreaker_hit(..., strict=True)`: a hit turns a stored like into a pass. If Jev cannot be asked the profile is not swiped and waits for the user. A profile with an empty bio has nothing to check and is swiped by its suggestion.
- **Limits:** `GET /swipes/limits` and `PUT /swipes/limits` with `{"swipes_per_run": 5, "swipes_per_day": 20}` (the defaults; columns on `users`). They count unattended swipes per app: per run of the job, and in any 24 hours. Allowed values are 1 to 10 per run and 1 to 100 per day. Keep them low: fast swiping is a ban signal.
- **Audit:** each swipe writes one entry: type `like` or `pass`, target `candidate:<swipe_candidates.id>`, trigger `swipe autopilot: jev dealbreaker` or `swipe autopilot: model pre-screen`. The row gets `unattended = true`, so it is not counted as a manual swipe.
