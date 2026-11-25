# Google Calendar holds

All in `app/calendar.py`; the table is `calendar_holds` (one row per slot held or confirmed for a match).

## What the owner sets up in Google Cloud

Do this once per server, at <https://console.cloud.google.com>:

1. Create a project.
2. In APIs & Services > Library, enable the **Google Calendar API**.
3. In APIs & Services > OAuth consent screen, choose user type **External**, and add the scopes `.../auth/calendar.events` and `.../auth/calendar.freebusy`. Add your own Google account under Test users.
4. Set the publishing status to **In production**. In **Testing**, Google expires the refresh token after 7 days and the calendar disconnects. Your own unverified app shows a warning page on connect; continue through it.
5. In APIs & Services > Credentials, create an **OAuth client ID** of type **Web application**. Add `https://<your server>/calendar/callback` as an authorized redirect URI (`http://localhost:8000/calendar/callback` for local use).
6. Give the server the three values. Compose passes them to the API and worker:

| Variable | Value |
| --- | --- |
| `GOOGLE_CLIENT_ID` | The OAuth client's ID |
| `GOOGLE_CLIENT_SECRET` | The OAuth client's secret |
| `GOOGLE_REDIRECT_URI` | The redirect URI from step 5, character for character |

## Connect

| Route | Does |
| --- | --- |
| `GET /calendar/connect` | Returns `{"url": "..."}`: Google's consent page. Open it in a browser. `503` while a variable above is unset. |
| `GET /calendar/callback?code=&state=` | Where Google sends the browser. Stores the refresh token and shows one line of text. It takes no API token: `state` names the user and is valid for 10 minutes. |
| `GET /calendar` | `{"connected": true}` once a refresh token is stored. |

The refresh token is stored in the token vault under the app name `google_calendar`. Never log it. Only the user's primary calendar is used. To disconnect, remove the app's access at <https://myaccount.google.com/permissions>; there is no disconnect route.

## Functions for the chat autopilot

All take the caller's transaction as `db`. Datetimes must be timezone-aware.

```python
from app import calendar

slots = calendar.free_slots(db, user_id, start, end, duration=timedelta(hours=2))  # [(start, end), ...]
sentence = calendar.offer_slots(db, user_id, card_id, draft_id, trigger="copilot: offered a time")  # "I'm free ... or ...", or None
hold_id = calendar.hold_slot(db, user_id, card_id, start, end, trigger="chat autopilot: proposed a time", draft_id=draft_id)
calendar.release_holds(db, user_id, card_id, trigger="match declined")  # draft_id=... for one draft's holds only
calendar.confirm_date(db, user_id, card_id, trigger="match agreed", start=start)  # True if a hold was confirmed
```

- `free_slots()` cuts the window into slots of `duration` from `start` and returns those that touch no busy time in Google and no row in `calendar_holds`. Choosing the window (which days and hours) is the caller's job.
- `offer_slots()` is how a draft offers a time: it picks up to 2 free evenings (19:00 to 21:00 on the next 7 days in `USER_TIMEZONE`, a fixed v1 window), holds each with `hold_slot(..., draft_id=)` and returns the English sentence to add to the draft. `None` when no evening is free.
- `hold_slot()` must be called for every slot a message offers. It creates a tentative event named "Hold: date with <name>". It raises `SlotTaken` if the slot is busy in Google or overlaps any slot held or confirmed for a match.
- Two matches never get the same slot because the database refuses it: `calendar_holds` has an exclusion constraint, so no two rows of one user overlap. A second hold on an overlapping slot fails even if two jobs race.
- `release_holds()` deletes the card's tentative events and their rows. Call it when the match declines. `PATCH /cards/{id}` with `stage: archived` calls it too.
- `confirm_date()` turns the hold that starts at `start` into a confirmed event named "Date with <name>" and releases the card's other holds. Without `start` it confirms only if the card has exactly one hold. `PATCH /cards/{id}` with `stage: date_set` calls it without `start`, so a card with several holds keeps them until code names the agreed slot.
- Code that sets a card's stage without the `PATCH` route must call `calendar.stage_changed(db, user_id, card_id, stage)`.
- A confirmed row stays and keeps its slot taken. Archiving the card later does not delete the event.
- Every hold, release and confirmation writes a `calendar_hold` entry to the audit log with target `card:<id> hold|release|confirm <start in UTC>` and the given trigger.
- All four raise `NotConnected` if the user has no stored refresh token, and `httpx.HTTPError` if Google refuses or cannot be reached; nothing is stored then. The `PATCH` route answers `502` and leaves the stage unchanged.
- Tests never reach Google: the autouse `gcal` fixture replaces `calendar.google`, the only object that calls Google. Set `gcal.busy` to `(start, end)` pairs and read `gcal.events`.
- Calls to the real Google API have not been tried: no Google credentials were available when this was written. Check the scopes, the free/busy response and the event fields in `GoogleCalendar` on the first real connect.
