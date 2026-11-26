# Status strip

What stops autopilot now, shown above the tab bar on every tab so the user never forgets it. The server lists the messages in `app/status.py`; the app's strip is `ios/DatingCRM/Components/StatusStrip.swift`.

| Route | Does |
| --- | --- |
| `GET /status` | The strip's messages in priority order. `[]` when nothing is paused, the AI budget is below its cap and no connector is broken. |

Each message is `{"kind", "app", "resets_at"}`. The server sends codes only; the app holds the copy. In this order:

1. `paused`, `app` null: the Pause on all apps.
2. `paused` with `app`: each app paused on its own, by name. Pauses come from `GET /autopilot/pause` (see "Autonomy and Pause"); a connector that breaks pauses its app, so it shows here too.
3. `budget_reached` with `resets_at`: the AI budget is reached. Spend counts the calendar month in UTC (`llm.spend()`), so `resets_at` is midnight UTC on the first of next month. A higher cap ends it at once.
4. `connector_alert` with `app`: each app whose state on Connected apps is `broken` (see "Sync"). Choosing copilot-only or pasting a fresh token answers the alert, so the app leaves the strip; its pause stays until resumed.

The clock for `resets_at` is `app.status.now`; tests replace it.

## On the phone

`MainTabView` applies `.modifier(StatusStrip(client:tab:))` to its `TabView`. The strip is the tab view's bottom accessory, on Liquid Glass, and is there only while `client.status()` returns a message. It shows the first message:

| Kind | Copy | Action |
| --- | --- | --- |
| `paused` | "Autopilot paused", or "Tinder paused" | Resume: `client.setPaused(false, app:)`, then reloads |
| `budget_reached` | "AI budget reached. Resets Dec 1" (`RelativeTime.day` of `resets_at`, in the phone's time zone) | None |
| `connector_alert` | "Tinder disconnected" | Reconnect: opens `ConnectedAppsView` in a sheet, then reloads |

The strip reloads on every tab change and every minute, so a pause made under Autopilot or a budget reached on the server shows within a minute. A failed load keeps the last strip. Its text stops growing at the xxxLarge text size, as the tab bar does, shrinks to 75% before truncating, and shows in the Large Content Viewer on a long press.

On iOS 26.0 an accessory cannot be hidden, so the tab view is rebuilt when the strip comes or goes and the tabs lose their place; iOS 26.1 and later hide it in place.
