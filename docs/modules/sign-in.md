# Sign-in

A user signs in with their phone number and a six-digit sign-in code sent by SMS (ADR 0006). A phone number with no account also needs an invite code, and the sign-in that uses it creates the account. Routes in `app/sign_in.py`, tokens in `app/auth.py`, invite codes in `app/invite_codes.py`, texts through `app/sms.py`.

## Routes

| Route | Body | Answers |
| --- | --- | --- |
| `POST /sign-in/code` | `{"phone": "+491701234567", "invite_code": "K7QX-M2PA"}`; `invite_code` is optional | `204`: the code was texted. `403 invite_code_needed`: no account has this number and no invite code came. `403 invite_code_invalid`: no account has this number and the invite code is unknown or used. `429 too_many_requests`: rate limit. `422`: not E.164. |
| `POST /sign-in` | `{"phone": ..., "code": "123456"}` | `200 {"token": ..., "new_account": true}`: `new_account` is true when this sign-in created the account. `401 wrong_code`. `410 code_expired`: expired, used, replaced, or never sent. `429 too_many_tries`. `403 invite_code_invalid`: the invite code created another account after this code was sent. |
| `POST /sign-out` | none, with the bearer token | `204`. Revokes the caller's token only, and unregisters the push device that token registered. |

Refusals carry their code in `detail`, for example `{"detail": "wrong_code"}`.

## Rules

- The phone number (E.164, unique on `users.phone`) is the account's identity. Email is optional; v1 accounts keep theirs.
- A sign-in code is six digits, stored as a SHA-256 of phone and code, valid for 10 minutes, and allows 5 tries. The sixth try is refused even with the right code.
- A phone number has one live code: a new request replaces the last, and a used code is gone.
- Code requests are limited to 5 per phone number and 20 per IP address in any hour. Refused requests count towards the IP limit, so numbers cannot be probed for free. The IP is the one uvicorn sees: behind a proxy, start uvicorn with `--forwarded-allow-ips` for that proxy, or every request shares the proxy's IP.
- Each signed-in device has its own API token (`api_tokens`, one row per device). `CurrentUser` carries `token_id`, the token of the request. A push device (`devices.api_token_id`) belongs to the token that registered it and is deleted with it.
- The v1 token moved to `api_tokens` in the migration `t48_phone_sign_in`, so it keeps working.

## Invite codes

- An invite code is one-time: it creates one account. The owner gives it to a person on the waitlist (a web page outside the app).
- A code request for a phone number with no account needs a valid, unused invite code; the code request stores it (`sign_in_codes.invite_code_id`). A phone number with an account never needs one, and an invite code sent with it is ignored.
- The invite code is used up (`invite_codes.used_at`) when the sign-in succeeds, in the same statement that checks it, so two numbers that each got a sign-in code with one invite code cannot both create an account.
- Eight characters without 0, O, 1, I or L, printed as `K7QX-M2PA`. Case, spaces and dashes do not matter when typed. Only a SHA-256 is stored, so a printed code cannot be shown again.
- Refused invite codes count towards the IP limit like any code request, which bounds guessing at 20 an hour per address.
- `invite_codes` has no `user_id`: an invite code belongs to no user. Both tenancy tests exempt it.

Create invite codes (one per line, three here):

```sh
uv run python -m app.invite_codes 3
```

## The `sms` seam

`app.sms.send(phone, body)` is the only function that texts a phone. For now it writes the text, code included, to the server log at `WARNING`; the SMS provider (#50) replaces its body. The text reads "123456 is your Dating CRM code. It expires in 10 minutes."

## Give an existing account a phone number

```sh
uv run python -m app.sign_in you@example.com +491701234567
```

The owner's v1 account can then sign in by SMS. `uv run python -m app.auth you@example.com` still creates an account and prints a token for the developer sign-in.

## iOS

`SignInView` (`ios/DatingCRM/Screens/SignInView.swift`): the phone number, then, only when the server answers `403` for a number with no account, an invite code field under it, then the sign-in code, with "Send a new code" after 30 seconds and each refusal in plain words under the field. A two-second press on the title opens the developer sign-in (server URL and API token). `Session.requestCode(phone:inviteCode:)` and `Session.signIn(phone:code:)` use the server in `ServerURL` (Info.plist). After a sign-in, `Session.isNewAccount` is true when it created the account (the server's `new_account`), so setup can start; it is not kept across launches. `APIClient.signIn` returns `SignedIn` (`token`, `newAccount`). A `403` on a code request without an invite code shows the invite code field; with one, it says the invite code is not valid or already used. `DCRM_INVITE=K7QX-M2PA` shows the field for scripted simulator checks. `Session.e164(_:)` turns a typed number into E.164. `Session.signOut()` calls `POST /sign-out`, then forgets the session. The token stays in the shared Keychain group and the URL in the App Group's defaults, so the share extension needs no change. Screenshots: `docs/design/screenshots/redesign/t48-sign-in-*`, and the invite code field in `t49-sign-in-invite-*`.

## Tests

- The autouse `sms` fixture replaces `app.sms.send`. `sms.sent` lists each `(phone, body)`; `sms.code(phone)` is the code in the last text to that number.
- `tests/test_sign_in.py` moves time by replacing `app.sign_in.now` (fixture `clock`).

## Not done

- The real SMS provider: #50.
