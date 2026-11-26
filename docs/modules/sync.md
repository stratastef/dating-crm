# Sync

`app/sync.py` copies an app's matches and messages into cards. It works for every connector listed in `CONNECTORS` there.

- **Start:** `PUT /connectors/{app}/token` with `{"token": "..."}` stores the token in the vault, deletes the user's alerts for the app and their copilot-only choice (so the connector is on again), marks the app's next sync as its first since this connect (a `first_syncs` row) and queues a `sync_matches` job with payload `{"app": app}`. It returns `204`, or `404` if the app has no connector. The phone's Connect and Reconnect call it.
- **Schedule:** `sync_matches` is a recurring job (`every=SYNC_INTERVAL`, 15 minutes). The recurring run has an empty payload and syncs every app in `CONNECTORS`. It skips an app, without failing, when the user has no token for it, the app is copilot-only or a read capability is switched off.
- **Cards:** a new match becomes a card in `matched`. `upsert_card()` in `app/cards.py` finds the card by `external_id`; on a later sync it changes only the name. A new match with no messages queues chat autopilot's opener, if it may act (see "Chat autopilot"), except on the first sync since a connect or reconnect: whichever sync of the app reads its matches first deletes the `first_syncs` row, and the matches it finds get no opener. A match the user purged is skipped (see "Find and purge").
- **Messages:** `upsert_message()` adds a message unless the card already has its `external_id`. A new message moves a card from `matched` to `chatting`. Sync never changes any other stage.
- **Fewer requests:** sync reads a match's messages only when the match has messages and its newest one is not stored yet.
- **Not built:** a match that disappears from the app (unmatched) keeps its card and stage.

## Connected apps

The phone's Connected apps screen (under You, and the setup step) reads and sets each dating app's connector here.

- **`GET /connectors`** (`ConnectedApp`) lists every app in `DATING_APPS` (`tinder`, `hinge`, `bumble`), in that order, as `{"app", "state", "alert"}`. `state` is the first that holds:
  1. `no_connector`: the app is not in `CONNECTORS`. The app drafts for it and the user copies.
  2. `copilot_only`: the user chose copilot-only.
  3. `broken`: an alert stopped the connector (see "Connectors"). `alert` is the newest one: `id`, `app`, `capability`, `reason` (`auth failure` or `ban signal`), `error`, `created_at`. It is `null` in every other state.
  4. `connected`: a session token is stored.
  5. `not_connected`.
- **`PUT /connectors/{app}/copilot-only`** marks an app copilot-only: it deletes the app's session token and alerts and stores the choice in `copilot_only_apps`. While the choice stands, `is_copilot_only()` is true, so nothing syncs, sends or swipes there and Send on its drafts gets `409`. A fresh token lifts it. `204`, or `404` if the app has no connector. A pause stays as it was.
- **Add a dating app:** add it to `DATING_APPS`; add its connector to `CONNECTORS` once one exists.

A connector's `read_matches` returns dicts with `id`, `name`, `has_messages` and `last_message_id` (`None` if unknown). Its `read_messages` returns dicts with `id`, `sender` (`me` or `them`), `body` and `sent_at`.

## On the phone

`ConnectedAppsView(client:)` lists each dating app from `client.connectedApps()` (`GET /connectors`, see "Sync") with its `ConnectorState`: Connected, broken with its alert and when it came (the alert line in the accent, since it waits on the user), Copilot only, Not connected, or No connector (Hinge, Bumble: the app drafts and the user copies). Connect or Reconnect opens `ConnectAppSheet(client:app:onConnected:)`, which shows `ConnectAppSheet.steps[app]` (Tinder's say a computer is needed) and a secure field for the session token, and calls `client.connect(app:token:)`. Copilot only asks first, then calls `client.chooseCopilotOnly(app:)`. The setup step can push `ConnectedAppsView`; anything that offers Reconnect can present `ConnectAppSheet` alone.
