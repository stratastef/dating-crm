# Today

The first screen (ADR 0005): what the user has to do, by time. All in `app/today.py`; the app's screen is `ios/DatingCRM/Screens/TodayView.swift`.

| Route | Does |
| --- | --- |
| `GET /today` | `{"review", "setup", "overdue", "today", "coming_up"}`: the review summary, the setup summary and the three groups. |

- **Review summary.** `review` is `{"count", "hot"}`: how many items wait in the review queue and how many of them are hot leads. It is counted from `GET /queue` itself, so Today, the Review tab badge and Review never disagree. Today shows review items only as this one row, so no item appears twice.
- **Items.** Each item is `{"kind", "card", "starts_at", "due_date", "days_late"}`. `card` is the card with its card summary (see "Cards and messages"). Kinds:
  - `date`: a confirmed calendar hold (see "Google Calendar holds"), with `starts_at`. Holds that were only offered are left out.
  - `next_action`: a card's next action with its due day in `due_date`. A due day without a next action is left out.
  - `stalled`: a Stalled card, which the app offers to revive or archive (the card's `suggested_actions`).
  - `rate_date`: a Dated card with no rating.
- **Groups**, by the user's day in the user's time zone:
  - `overdue`: next actions past their due day, most days late first, each with `days_late`. A next action due today is not overdue.
  - `today`: confirmed dates starting today, by time; next actions due today; then Stalled cards and Dated cards with no rating.
  - `coming_up`: confirmed dates and next actions on the next seven days, by day, dates first on each day.
- Archived cards are never on Today, even with a next action or a confirmed date.
- **Time zone.** The app sends the phone's time zone on each launch with `PATCH /settings {"time_zone": "Europe/Berlin"}`; an unknown name is `422`. It is `UTC` until the app first sends one. `user_zone(db, user_id)` in `app/settings.py` returns it as a `ZoneInfo`: use it for anything that follows the user's day or hour. The clock is `app.today.now`; tests replace it (fixture `clock` in `tests/test_today.py`).
- **Setup summary.** `setup` is `{"steps_left": n}`: how many setup steps are not done. It is `null` once the user dismissed "Finish setup" or no step is left (see "Setup").

## iOS

`TodayView` opens on the review count, large in the accent color, over a `MeshGradient` color field that runs under the status bar and scrolls away with the content. The field is full at 3 or more waiting items, softer at 1 or 2, and gone at 0. The count rolls (`contentTransition(.numericText())`); with Reduce Motion or Low Power Mode on (`motionReduced`), it fades and the field is hidden. Tapping the count opens Review.

Under the count, "Finish setup" says how many setup steps are left while `setup` is not null; it opens setup on those steps, and its `xmark` hides it, with Undo in a toast (see "Setup"). Below it come the three groups, each with a count in its header; Overdue's header is in the accent color. A row is the card's face, the name ("Date with Ada" for a date), what to do, and the time: the date's time, the due day ("2 days late" in the accent color), how long a Stalled chat has been quiet, or the day of the date to rate. A row opens its card; a date to rate opens the rating sheet. With all three groups empty, Today says "Nothing for today" in New York. Pull to refresh; the screen reloads each time it appears. Each load sets the Review tab's badge to the review count.

`APIClient.today()` is `GET /today`; `APIClient.setTimeZone(_:)` is the launch call above. Today sends it once, before its first load.

## Limits

- The color field is still: its warmth follows the count, but it does not drift.
- Seen on screen in light, dark, at the largest accessibility size and empty (`docs/design/screenshots/redesign/t54-*`). Not seen: the count rolling, Reduce Motion, the rating sheet and opening a card from a row (no taps in the simulator checks), and VoiceOver.
