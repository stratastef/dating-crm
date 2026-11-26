# Tinder connector

`app/tinder.py` reads your own Tinder account with your own web session token. It supports `read_matches`, `read_messages`, `send`, `read_candidates`, `like` and `pass`, and the paid items `super_like` and `boost`, which are spent only on the user's approval (see "Paid items"). A message goes out when the user taps send on a draft (see "Drafts"), or on its own only with chat autonomy at `autopilot` or `full_autopilot` (see "Chat autopilot"). A like or pass goes out when the user swipes on a candidate (see "Swipe copilot"), or on its own only once the user turns swipe autopilot on (see "Swipe autopilot"). Set `CONNECTOR_DISABLED_CAPABILITIES=tinder:send` to keep it read-only. Tinder's terms do not allow this API use; see Risks in the spec.

## Capture and submit your token

1. On your computer, log in at <https://tinder.com> in a desktop browser.
2. Open the developer tools (F12), then the Network tab, and reload the page.
3. Click any request to `api.gotinder.com` and copy the value of the `X-Auth-Token` request header. The same value is in Application > Local Storage > `https://tinder.com` under the key `TinderWeb/APIToken`.
4. Send it to your server. `$API_TOKEN` is your Dating CRM token from `python -m app.auth`:

```sh
curl -X PUT http://localhost:8000/connectors/tinder/token \
  -H "Authorization: Bearer $API_TOKEN" -H "Content-Type: application/json" \
  -d '{"token": "<the X-Auth-Token value>"}'
```

The worker syncs within a second and then every 15 minutes. Check with `GET /cards?app=tinder`. The token is a password for your Tinder account: do not paste it anywhere else. When Tinder logs the web session out, one sync fails, the app becomes copilot-only and an alert is stored. Later syncs skip Tinder until you repeat the steps.

## Assumptions to confirm against your real account

The connector was built from public write-ups of the web API and was never run against Tinder. The fixtures in `tests/fixtures/tinder/` are written by hand in that shape; they are not recordings. Compare each row with a real response in the Network tab and fix `app/tinder.py` and the fixtures where they differ.

| Assumption | Used for |
| --- | --- |
| The token is in `localStorage` as `TinderWeb/APIToken` and is sent as the `X-Auth-Token` header | Capture, every request |
| `X-Auth-Token` is the only header Tinder requires (no `app-version`, `platform` or device ID headers) | Every request |
| `GET https://api.gotinder.com/v2/matches?count=60&message=0` lists matches without messages, and `message=1` those with messages | `read_matches`, `has_messages` |
| `count=60` is accepted on both endpoints | Page size |
| The response body is `{"data": {"matches": [...], "next_page_token": "..."}}`, and `next_page_token` is absent on the last page and sent back as `page_token` | Paging |
| A match has `_id` and `person._id`, `person.name` | Card `external_id` and name, telling senders apart |
| A match from `message=1` has `messages`, a list that includes its newest message, each with `_id` and `sent_date` | `last_message_id`. If the list is missing or empty, sync reads that match's messages on every run. If it holds only older messages, sync misses new ones |
| `GET /v2/matches/{match_id}/messages?count=60` returns `{"data": {"messages": [...], "next_page_token": "..."}}` | `read_messages` |
| A message has `_id`, `from` (a user ID), `message` (the text) and `sent_date` (ISO 8601) | Message `external_id`, sender, body, time |
| A message whose `from` is not `person._id` is yours | `sender` |
| `POST https://api.gotinder.com/user/matches/{match_id}` with the JSON body `{"message": "<text>"}` sends a message (no `/v2` prefix, no other body field such as a temporary message ID) | `send` |
| That request answers `200` with the sent message as the whole body (not wrapped in `data`), with `_id` and `sent_date` as in a read message | Message `external_id` and time. If `_id` differs from the ID a later read gives, sync adds the message a second time |
| Any answer other than `2xx` means the message may or may not have been sent | A failed send is never retried |
| An expired token gives HTTP `401` | Fallback to copilot |
| `GET /v2/recs/core` returns `{"data": {"results": [{"user": {...}}]}}`, and `results` is absent or empty when nobody is left | `read_candidates` |
| A candidate's `user` has `_id`, `name`, optional `bio` and `photos`, a list of objects with `url` | Candidate `profile_id`, name, bio, photo URLs |
| `GET /like/{user _id}` likes and `GET /pass/{user _id}` passes, with no body, query or `s_number` needed, and both give HTTP `200` | `like`, `pass` |
| The like is the free one: Super Like is a different endpoint (`/like/{id}/super`), which `like` never calls | A like spends no paid item |
| `POST /like/{user _id}/super` with no body spends one Super Like the account holds and gives HTTP `200` | `super_like` (see "Paid items") |
| `POST /boost` with no body starts one Boost the account holds and gives HTTP `200` | `boost` |
| With none left, both still give HTTP `200` and the body has `"limit_exceeded": true`. Neither request buys an item or charges a payment method: buying is a separate purchase flow the connector never calls | The proposal ends as `failed` and nothing is logged. If Tinder answers another way, a spend that did not happen is logged as spent, or the app becomes copilot-only |
| The body of a spent Super Like or Boost needs no reading (`match`, `super_likes.remaining`, `boost.expires_at` are ignored) | `super_like`, `boost` |
| A like when no free likes are left still gives HTTP `200` (the body has `likes_remaining: 0` or `rate_limited_until`) | Such a like is reported as applied although Tinder dropped it |
| One sync every 15 minutes does not trip Tinder's rate limits or bot detection | `SYNC_INTERVAL` |
