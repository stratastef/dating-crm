# Fixtures

`tinder/` holds responses **written by hand** from public write-ups. None is a recording. Every shape they assume is listed in `docs/modules/tinder-connector.md`.

## Replace a hand-written fixture with a recording

Only the account owner can do this; it needs their own signed-in session.

1. Sign in at tinder.com, open the browser's Network tab, and trigger the call (open matches, open a chat, load the swipe deck).
2. Save the response body as JSON over the matching file in `tinder/`.
3. Scrub it before committing: replace every name, bio, photo URL, message text and ID with invented values of the same shape and length. A fixture holds no real person.
4. Run `uv run pytest tests/test_tinder.py tests/test_swipes.py tests/test_send.py`. Fix `app/tinder.py` where the real shape differs, and strike the confirmed row from the assumptions table.

The spec's REA commands (`inspect-web-network-capture`, `capture-browser-scenario`) capture the same calls in bulk.

## Other services

Jev (through treg), APNs and Google Calendar have no fixtures: tests stub one function each (`jev.ask`, `push.post`, `calendar.google`). The Jev request shape and price are unconfirmed; see `docs/modules/jev-checks.md`.
