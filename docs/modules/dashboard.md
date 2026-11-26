# Dashboard

Routes are in `app/dashboard.py`; the table is `app_time` (one row per report).

| Route | Does |
| --- | --- |
| `POST /time` with `{"seconds": 90}` | Record time the user spent in the app. 1 second to 1 day per report; returns `204`. |
| `GET /dashboard` | The weekly series, the headline, this month's funnel and AI spend (below). |

`GET /dashboard` returns:

- `weeks`: one entry per week with recorded time or a good date, oldest first: `week` (its Monday), `good_dates`, `hours`, `good_dates_per_hour`.
- `this_week`: good dates per hour this week, the headline. `null` with no time recorded this week.
- `four_week_average`: good dates per hour over the four weeks before this one (all their good dates over all their hours). `null` with no time recorded in them.
- `funnel`: cards that reached each stage this month: `matched`, `chatting`, `date_set`, `dated`, and `good` (good dates rated this month).
- `spend_per_good_date_usd`: this month's AI spend over this month's good dates. `null` with no good date this month.
- `budget`: this month's AI spend against the cap, as `GET /budget` (`spend_usd`, `cap_usd`, `paused`).

- A week starts on Monday in UTC, and a month on the 1st in UTC (as the AI budget's).
- A good date (`is_good_date()`: rated 4 or 5) counts in the week and month of the card's `date_rated_at`: the moment of its first rating, not the day of the date.
- Funnel: Matched counts cards created this month. A trigger on `cards` sets `chatting_at`, `date_set_at` and `dated_at` the first time a card reaches that stage or a later one, whoever moves it; they never move or clear, so an archived card still counts in the stages it reached. A card added straight into a later stage counts in every stage before it. Number swapped and Seeing them are not funnel stages.
- Limit: hours are only the time the iOS app was in the foreground, as the app reports it; time in the dating apps is not counted, and a stretch is lost if the app is killed or suspended before it reports.
- Limit: cards from before the funnel existed count every stage they passed at their last stage change; archived ones count none.

## On the phone

You opens with the headline (`DashboardHeadline`): this week's good dates per hour, the four-week average and "Good = rated 4 or 5". It links to `DashboardView`: the headline, a weekly chart, this month's funnel, AI spend per good date and this month's spend as "$8.20 of $30" (`Budget.spentOfCap`), then the weeks.
