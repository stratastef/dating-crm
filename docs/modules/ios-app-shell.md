# iOS app shell and shared components

The signed-in app is `MainTabView` (`ios/DatingCRM/Screens/MainTabView.swift`): a five-tab `TabView` that opens on Today (ADR 0005). Each tab owns its `NavigationStack`, except Pipeline, whose `BoardView` keeps its own for push taps. iOS 26 is the minimum (ADR 0002).

| Tab | Shows now |
| --- | --- |
| Today | `TodayView` (see "Today"). Tapping the review count switches to Review. |
| Review | `QueueView`. The tab's badge is the review count from Today's last load. |
| Pipeline | `BoardView`, still under the seven stages. A tapped push switches to this tab and opens the card. Search (minimized to a toolbar button) filters the loaded cards by name; the plus button opens `NewCardSheet` to add a card by hand. |
| Swipe | `SwipeView` |
| You | `YouView`: Dashboard, Autopilot (`AutopilotView`), Preferences, Connected apps (`ConnectedAppsView`), Calendar (`CalendarView`), Profile (Photos, Voice), Account (Settings, Sign out, which asks first) |

## Look (ADR 0009, `docs/design/mockups/a3-combined.html`)

`MainTabView` sets three things for every screen: `.tint(.primary)`, so buttons, links and the selected tab are black or white; `.listStyle(.plain)`; and `motionReduced` (below).

The shared components are in `ios/DatingCRM/Components/`, one file each:

| Type | File | Use |
| --- | --- | --- |
| `.accent`, `.accentSoft`, `.secondaryText` | `Palette.swift` | Colors as `ShapeStyle`s: `.foregroundStyle(.accent)`. The accent only marks what waits on the user. Use `.secondaryText` for grey text: the system `.secondary` is under 4.5:1 on white. |
| `.primaryCapsule`, `.secondaryCapsule` | `Palette.swift` | Button styles: a capsule in the label color, or on the system fill. 44 pt high. |
| `AIMarker(.draft / .autopilot / .suggests)` | `AIMarker.swift` | The sparkles symbol and its label; VoiceOver reads the spoken label. |
| `Badge(.hot / .stalled / .overdue(days:))` | `Badge.swift` | Icon plus text. Hot and Overdue are accent, Stalled grey. |
| `Toast` and `.toast($toast)` | `Toast.swift` | On Liquid Glass at the bottom for 5 seconds; Undo when `undo` is set. VoiceOver announces the text. |
| `RelativeTime.since/day/due`, `TimeAgoText` | `RelativeTime.swift` | "10m", "4d", "Today", "Sat", "2 days late"; the year only when it is not this year. |
| `Avatar(name:photo:)` | `Avatar.swift` | The photo at 48 pt, or the monogram in New York on the soft accent. Puts the row's separator 14 pt past itself. |
| `AdaptiveStack` | `AdaptiveStack.swift` | Side by side, stacked at accessibility text sizes. For row metadata and button pairs. |
| `AutonomySections(levels:choose:)` | `AutonomySections.swift` | One list section per job (Chat, Optimize profiles, Swipe) listing the four levels with `AutonomyLevel.summary`. The host loads the levels and saves the choice. Used by `AutopilotView`; meant for the setup step too. |
| `.autosave(value, saved:) { save }` | `Autosave.swift` | Saves a second after the last change and when the view goes away. Pass `value` as `saved` until loaded. Ignore errors from a cancelled save. |
| `GrowingField(label:prompt:text:)` | `GrowingField.swift` | A text field that grows, hides the keyboard on return and takes taps on its whole 44 pt row. `label` is read by VoiceOver. |
| `ErrorRow(text:retry:)` | `ErrorRow.swift` | A failed load or save next to what failed, in primary text with a red icon; tapping it retries. Borderless, so it can share a row with a field. |
| `\.motionReduced` | `Motion.swift` | True with Reduce Motion or Low Power Mode on. Read it before any spring, ring or color field and use a fade instead. |

Type: SF Pro text styles. New York (`.fontDesign(.serif)`) only for explanations, empty states, setup and monograms.

## Editing screens

`VoiceView` (the voice questionnaire, rendered from the server's `questions`) and `PreferencesView` follow one pattern: load once, keep the server's copy as `saved`, `.autosave` the edited copy, and show `ErrorRow` under each field whose value differs from `saved` after a failed save. Lists dismiss the keyboard on scroll (`.scrollDismissesKeyboard(.immediately)`). Push either one; they set their own title and toolbar.

## Card rows

Every `Card` carries its card summary (see "Cards and messages"): `stageChangedAt`, `stalled`, `lastMessage` (`LastMessage`: sender, body, sent time), `hot`, `pendingDraft`, `leadPhotoUrl`. A row reads only these, never `/queue`. `BoardView.CardRow` is the A3 row: `Avatar` with the lead photo, the name with `TimeAgoText(date: card.lastActivity)` at the trailing edge (the last message, or the last stage change), "Chatting · Tinder", then the Hot, Stalled and Overdue badges. Name and time, and caption and badges, are each an `AdaptiveStack`, so they stack at accessibility sizes.

## Connected apps

`ConnectedAppsView(client:)` lists each dating app from `client.connectedApps()` (`GET /connectors`, see "Sync") with its `ConnectorState`: Connected, broken with its alert and when it came (the alert line in the accent, since it waits on the user), Copilot only, Not connected, or No connector (Hinge, Bumble: the app drafts and the user copies). Connect or Reconnect opens `ConnectAppSheet(client:app:onConnected:)`, which shows `ConnectAppSheet.steps[app]` (Tinder's say a computer is needed) and a secure field for the session token, and calls `client.connect(app:token:)`. Copilot only asks first, then calls `client.chooseCopilotOnly(app:)`. The setup step can push `ConnectedAppsView`; anything that offers Reconnect can present `ConnectAppSheet` alone.

## Calendar

`CalendarView(client:)` shows whether Google Calendar is connected (`client.calendarConnected()`, `GET /calendar`, see "Google Calendar holds") with Connect, or Reconnect once connected. Connect gets Google's consent page from `client.calendarConsentURL()` (`GET /calendar/connect`) and opens it in an ephemeral `ASWebAuthenticationSession` that waits for the `datingcrm` scheme; the server's callback sends it there. The view then asks the server again and shows a toast, or a plain line when it is still not connected: Google refused, the user closed the page, or the server answered `503` (no Google OAuth client set up). The session is UIKit's, not SwiftUI's `webAuthenticationSession`, which failed on the simulator with `presentationContextNotProvided`. The setup step can push `CalendarView` as is.

## API dates

`APIClient` decodes a plain day (`2026-12-01`, local midnight) or a full timestamp (`2026-11-20T10:00:00.123456Z` or with an offset). It encodes plain days only. `Message.sentAt` is the first timestamp the app reads.

## Simulator checks

Besides the Debug sign-in (`DCRM_SERVER`, `DCRM_TOKEN`) and `DCRM_TAB`, `DCRM_OPEN=voice`, `DCRM_OPEN=preferences`, `DCRM_OPEN=connected-apps` or `DCRM_OPEN=calendar` pushes that screen under You on launch: `SIMCTL_CHILD_DCRM_TAB=you SIMCTL_CHILD_DCRM_OPEN=voice xcrun simctl launch …`.

## Limits

- The Review badge is the system red, not the accent: `UITabBarItem.appearance().badgeColor` has no effect on the SwiftUI `TabView`. It updates when Today loads, not when Review clears an item.
- Not verified on screen: typing, autosave, the save error under a field and Edit on Voice and Preferences (screenshots only, no taps).
- Not verified on screen: the toast (no screen shows one yet) and VoiceOver reading the AI marker and badges.
- Error text is still system red, under 4.5:1 on white, outside `ErrorRow`. Settings is still a grey grouped form until its ticket.
