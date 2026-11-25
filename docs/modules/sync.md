# Sync

`app/sync.py` copies an app's matches and messages into cards. It works for every connector listed in `CONNECTORS` there.

- **Start:** `PUT /connectors/{app}/token` with `{"token": "..."}` stores the token in the vault, deletes the user's alerts for the app (so the connector is on again) and queues a `sync_matches` job with payload `{"app": app}`. It returns `204`, or `404` if the app has no connector.
- **Schedule:** `sync_matches` is a recurring job (`every=SYNC_INTERVAL`, 15 minutes). The recurring run has an empty payload and syncs every app in `CONNECTORS`. It skips an app, without failing, when the user has no token for it, the app is copilot-only or a read capability is switched off.
- **Cards:** a new match becomes a card in `matched`. `upsert_card()` in `app/cards.py` finds the card by `external_id`; on a later sync it changes only the name. A match the user purged is skipped (see "Find and purge").
- **Messages:** `upsert_message()` adds a message unless the card already has its `external_id`. A new message moves a card from `matched` to `chatting`. Sync never changes any other stage.
- **Fewer requests:** sync reads a match's messages only when the match has messages and its newest one is not stored yet.
- **Not built:** a match that disappears from the app (unmatched) keeps its card and stage.

A connector's `read_matches` returns dicts with `id`, `name`, `has_messages` and `last_message_id` (`None` if unknown). Its `read_messages` returns dicts with `id`, `sender` (`me` or `them`), `body` and `sent_at`.
