# Sign-in

A user signs in with their phone number and a six-digit sign-in code sent by SMS (ADR 0006). Routes in `app/sign_in.py`, tokens in `app/auth.py`, texts through `app/sms.py`.

## Routes

| Route | Body | Answers |
| --- | --- | --- |
| `POST /sign-in/code` | `{"phone": "+491701234567"}` | `204`: the code was texted. `403 invite_code_needed`: no account has this number. `429 too_many_requests`: rate limit. `422`: not E.164. |
| `POST /sign-in` | `{"phone": ..., "code": "123456"}` | `200 {"token": ...}`. `401 wrong_code`. `410 code_expired`: expired, used, replaced, or never sent. `429 too_many_tries`. |
| `POST /sign-out` | none, with the bearer token | `204`. Revokes the caller's token only, and unregisters the push device that token registered. |

Refusals carry their code in `detail`, for example `{"detail": "wrong_code"}`.

## Rules

- The phone number (E.164, unique on `users.phone`) is the account's identity. Email is optional; v1 accounts keep theirs.
- A sign-in code is six digits, stored as a SHA-256 of phone and code, valid for 10 minutes, and allows 5 tries. The sixth try is refused even with the right code.
- A phone number has one live code: a new request replaces the last, and a used code is gone.
- Code requests are limited to 5 per phone number and 20 per IP address in any hour. Refused requests count towards the IP limit, so numbers cannot be probed for free. The IP is the one uvicorn sees: behind a proxy, start uvicorn with `--forwarded-allow-ips` for that proxy, or every request shares the proxy's IP.
- Each signed-in device has its own API token (`api_tokens`, one row per device). `CurrentUser` carries `token_id`, the token of the request. A push device (`devices.api_token_id`) belongs to the token that registered it and is deleted with it.
- The v1 token moved to `api_tokens` in the migration `t48_phone_sign_in`, so it keeps working.

## The `sms` seam

`app.sms.send(phone, body)` is the only function that texts a phone. For now it writes the text, code included, to the server log at `WARNING`; the SMS provider (#50) replaces its body. The text reads "123456 is your Dating CRM code. It expires in 10 minutes."

## Give an existing account a phone number

```sh
uv run python -m app.sign_in you@example.com +491701234567
```

The owner's v1 account can then sign in by SMS. `uv run python -m app.auth you@example.com` still creates an account and prints a token for the developer sign-in.

## iOS

`SignInView` (`ios/DatingCRM/Screens/SignInView.swift`): the phone number, then the sign-in code, with "Send a new code" after 30 seconds and each refusal in plain words under the field. A two-second press on the title opens the developer sign-in (server URL and API token). `Session.requestCode(phone:)` and `Session.signIn(phone:code:)` use the server in `ServerURL` (Info.plist); `Session.e164(_:)` turns a typed number into E.164. `Session.signOut()` calls `POST /sign-out`, then forgets the session. The token stays in the shared Keychain group and the URL in the App Group's defaults, so the share extension needs no change. Screenshots: `docs/design/screenshots/redesign/t48-sign-in-*`.

## Tests

- The autouse `sms` fixture replaces `app.sms.send`. `sms.sent` lists each `(phone, body)`; `sms.code(phone)` is the code in the last text to that number.
- `tests/test_sign_in.py` moves time by replacing `app.sign_in.now` (fixture `clock`).

## Not done

- Invite codes and creating an account at sign-in: #49. A code request for a number with no account is stored with `user_id` null and no code.
- The real SMS provider: #50.
