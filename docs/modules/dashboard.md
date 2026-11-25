# Dashboard

Routes are in `app/dashboard.py`; the table is `app_time` (one row per report).

| Route | Does |
| --- | --- |
| `POST /time` with `{"seconds": 90}` | Record time the user spent in the app. 1 second to 1 day per report; returns `204`. |
| `GET /dashboard` | One entry per week with recorded time or a good date, oldest first: `week` (its Monday), `good_dates`, `hours`, `good_dates_per_hour`. |

- A week starts on Monday in UTC. `good_dates_per_hour` is `null` for a week with no recorded time.
- A good date (`is_good_date()`) counts in the week of the card's `date_rated_at`: the moment of its first rating, not the day of the date.
- Limit: hours are only the time the iOS app was in the foreground, as the app reports it; time in the dating apps is not counted, and a stretch is lost if the app is killed or suspended before it reports.
