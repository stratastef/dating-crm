# Push notifications

All in `app/push.py`. To notify a user, call one function from a route or a job handler:

```python
from app.push import send_push

send_push(db, user_id, "Hot lead", "Ada replied", card_id=card_id)
```

- The push goes to every device the user registered. With `card_id`, tapping it opens that card in the app; without, it opens the app.
- It is best effort and never raises for an APNs failure: a refusal or a network error is logged as a warning.
- The iOS app registers its device with `POST /devices` and body `{"token": "<APNs device token in hex>"}`. A token belongs to the user who registered it last. When Apple answers `410` or `BadDeviceToken` for a token, its row in `devices` is deleted.
- Settings, passed by Compose to the API and worker. While any of the first four is unset, `send_push()` sends nothing and logs one line at `INFO`.

| Variable | Value |
| --- | --- |
| `APNS_KEY` | The contents of the `.p8` key from the Apple developer account. Line breaks may be written as `\n`. |
| `APNS_KEY_ID` | The key's 10-character ID |
| `APNS_TEAM_ID` | The developer team ID |
| `APNS_BUNDLE_ID` | The app's bundle identifier, `com.datingcrm.app` unless you changed it |
| `APNS_SANDBOX` | Set to `1` when the app is run from Xcode. Leave unset for TestFlight and App Store builds. |

- Tests never reach Apple: the autouse `apns` fixture replaces `post()`, the only function that calls APNs, and sets throwaway settings. Read `apns.sent` (each has `url`, `headers`, `payload`) to see what was pushed, and set `apns.answers["<token>"] = (410, "Unregistered")` to choose Apple's answer for a device.
- Sending to the real APNs has not been tried: no Apple developer account was available when this was written.
