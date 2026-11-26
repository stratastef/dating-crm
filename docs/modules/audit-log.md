# Audit log

Every autopilot action must call `record_action(connection, user_id, type=..., app=..., target=..., trigger=...)` from `app.audit`, in the same transaction as the action. `type` is one of `message`, `like`, `pass`, `profile_change`, `calendar_hold`, `purge`, `super_like`, `rose`, `boost`.
The `audit_log` table is append-only (a trigger rejects `UPDATE` and `DELETE`). `GET /audit-log?app=&type=` lists the current user's entries, newest first. The app shows it under You as the Activity log. Each entry's `name` is the person its `target` is about, read from their card or swipe candidate at request time (so a renamed card shows the new name); it is null for the user's own things and for `match:` targets.

`target` is one of these, alone or followed by a space and details (`card:7 hold 2026-12-01T19:00:00+00:00`):

| `target` starts with | About | Written by |
| --- | --- | --- |
| `card:<cards.id>` | A match | `message` (a sent draft), `calendar_hold`, `purge` of a card |
| `match:<external_id>` | A match, by the app's ID, for code that has no card. Nothing writes it today; the purge deletes it. | |
| `candidate:<swipe_candidates.id>` | A profile the user has not matched with | `like` and `pass` by swipe autopilot, `super_like`, `rose`, `purge` of a candidate |
| `account` | The user's own account on that app | `boost` |
| `bio` | The user's own bio on that app | `profile_change` |
| `photo:<photos.id>` | One of the user's own photos; `app` is `all` | `profile_change` |

An entry about another person must name them only at the start of `target`, in one of the first three forms. It must never hold their name or message text: a purge finds the entries to delete by that start of `target` alone (the `cards_purge_audit_log` and `swipe_candidates_purge_audit_log` triggers). A new form of target for a person needs its own purge.
