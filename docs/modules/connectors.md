# Connectors

The contract is in `app/connectors.py`. The capabilities are `read_matches`, `read_messages`, `read_candidates`, `send`, `like` and `pass`, and the paid items `super_like`, `rose` and `boost`. A profile from `read_candidates` may carry `cost`, what a paid item on it costs as the app shows it; a proposal for the profile keeps it. `call()` refuses a paid item; only an approved proposal spends one (see "Paid items").

Add a connector: subclass `Connector`, set `app`, declare the `capabilities` it supports and implement the method for each one (`pass` is the method `pass_`). Leave a capability out of `capabilities` to leave it out of the build. Each method receives the session token as its first argument. A method raises any exception when the app refuses or breaks.

```python
class TinderConnector(Connector):
    app = "tinder"
    capabilities = frozenset({"read_matches", "read_messages", "send"})

    def read_matches(self, token: str) -> list[dict]: ...
    def read_messages(self, token: str, match_id: str) -> list[dict]: ...
    def send(self, token: str, match_id: str, text: str) -> dict: ...  # the sent message: `id`, `sent_at`
```

Never call a connector method directly. Go through `call()`, which reads the user's token from the vault, passes it to the method and enforces the rules below:

```python
matches = call(db, user_id, TinderConnector(), "read_matches")
messages = call(db, user_id, TinderConnector(), "read_messages", match_id)
```

- **Switch a capability off:** set `CONNECTOR_DISABLED_CAPABILITIES=tinder:send,hinge:like` (comma-separated `app:capability`).
- **Unavailable:** `unavailable(db, user_id, connector, capability)` returns the reason, or `None`. `call()` raises `CapabilityUnavailable` and does not touch the app when the capability is not declared, is disabled, the app is copilot-only, or the user has no stored token for the app.
- **Transient errors change nothing:** if the connector method raises anything but an HTTP 401 or 403 (a timeout, a 5xx, a 429), `call()` logs it and raises `CapabilityFailed`. No alert is stored, nothing is paused and no push is sent: the app stays on, and a job that fails this way is retried by the job queue.
- **Fallback to copilot:** if the connector method raises an auth failure or ban signal (see below), `call()` inserts a row in `connector_alerts` (`user_id`, `app`, `capability`, `error` = the exception's class name, plus the status code for an HTTP error, such as `HTTPStatusError 401`; never its text or URL, which can hold match and profile IDs and would outlive a purge; the full error is logged) and raises `CapabilityFailed`, with the connector's exception as `__cause__`. The row is written in its own transaction, so it survives the failed job's rollback. That row is both the alert and the fallback: `is_copilot_only(db, user_id, app)` is true while the user has any alert for the app, or chose to keep it copilot-only (see "Sync", Connected apps), and every capability of that app is then unavailable for that user. `alerts(db, user_id)` lists them. Delete the user's rows for an app to re-enable its connector.
- **Ban detection:** `classify(error)` sorts the connector's exception into `auth failure` (HTTP 401), `ban signal` (HTTP 403) or `transient` (anything else). An auth failure or ban signal is stored in the alert's `reason`, calls `pause(user_id, app, reason)` in the same transaction as the alert, so that app's autopilot stops for that user, and sends a push. `GET /connectors/alerts` returns the user's alerts (`id`, `app`, `capability`, `reason`, `error`, `created_at`), newest first. A fresh token lifts the copilot-only fallback but not the pause: resume with `POST /autopilot/resume?app=...`.

Test a connector's callers with a fake like `FakeConnector` in `tests/test_connectors.py`.
