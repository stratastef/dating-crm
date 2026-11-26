# Preferences

Routes are in `app/preferences.py`; the table is `preferences` (append-only, one row per saved version). Preferences are `{"wishes": "...", "must_haves": ["..."], "dealbreakers": ["..."]}`.

| Route | Does |
| --- | --- |
| `GET /preferences` | The version in force, with its `version` number. Version `0` and empty until the first save. |
| `PUT /preferences` | Store the body as the next version. Earlier versions are kept. |
| `GET /preferences/versions` | Every version, oldest first, each with `created_at`: the moment it came into force. |

Server code reads the version in force with `current_preferences(db, user_id)` from `app.preferences`; it returns `version`, `wishes`, `must_haves` and `dealbreakers`. Swipes read it (a dealbreaker Jev finds in a bio is a pass) and so does every draft's prompt.

The app edits them on `PreferencesView` under You (see "iOS app shell"); it saves as the user types and drops rows left blank.
