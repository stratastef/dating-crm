# iOS app shell and shared components

The signed-in app is `MainTabView` (`ios/DatingCRM/Screens/MainTabView.swift`): a five-tab `TabView` that opens on Today (ADR 0005). Each tab owns its `NavigationStack`, except Pipeline, whose `PipelineView` keeps its own for push taps. iOS 26 is the minimum (ADR 0002).

| Tab | Shows now |
| --- | --- |
| Today | `TodayView` (see "Today"). Tapping the review count switches to Review. |
| Review | `QueueView`: the review queue as faces in glass (see "Review"). The tab's badge is the review count from Today's last load. |
| Pipeline | `PipelineView`: `GET /pipeline` grouped by who acts next (see "Pipeline" below). A tapped push switches to this tab and opens the card. Search (minimized to a toolbar button) filters the loaded cards by name and opens every group; the plus button opens `NewCardSheet` to add a card by hand. |
| Swipe | `SwipeView`: the Off state, one at a time or the list, as the Swipe layout says (see "Swipe copilot", On the phone) |
| You | `YouView`: Dashboard, Autopilot (`AutopilotView`), Preferences, Swipe layout (`SwipeLayoutSection`), Connected apps (`ConnectedAppsView`), Calendar (`CalendarView`), Profile (Photos, Voice), Account (Settings, Sign out, which asks first) |

## Look (ADR 0009, `docs/design/mockups/a3-combined.html`)

`MainTabView` sets three things for every screen: `.tint(.primary)`, so buttons, links and the selected tab are black or white; `.listStyle(.plain)`; and `motionReduced` (below).

Above the tab bar, on every tab, the status strip (`StatusStrip`, see "Status strip") shows what stops autopilot, with Resume or Reconnect.

The shared components are in `ios/DatingCRM/Components/`, one file each:

| Type | File | Use |
| --- | --- | --- |
| `.accent`, `.accentSoft`, `.secondaryText` | `Palette.swift` | Colors as `ShapeStyle`s: `.foregroundStyle(.accent)`. The accent only marks what waits on the user. Use `.secondaryText` for grey text: the system `.secondary` is under 4.5:1 on white. |
| `.primaryCapsule`, `.secondaryCapsule` | `Palette.swift` | Button styles: a capsule in the label color, or on the system fill. 44 pt high. |
| `AIMarker(.draft / .autopilot / .suggests)` | `AIMarker.swift` | The sparkles symbol and its label; VoiceOver reads the spoken label. |
| `Badge(.hot / .stalled / .overdue(days:))` | `Badge.swift` | Icon plus text. Hot and Overdue are accent, Stalled grey. |
| `Toast` and `.toast($toast)` | `Toast.swift` | On Liquid Glass at the bottom for 5 seconds; Undo when `undo` is set. VoiceOver announces the text. |
| `Held(after:) { action }` | `Held.swift` | Runs the action after 5 seconds unless `undo()` comes first; `undo()` is false once it started. Pair it with a toast's Undo for what the server cannot take back (a swipe). |
| `SwipeLayoutSection(client:)` | `SwipeLayoutSection.swift` | The Swipe layout choice as one list section that loads and saves itself. Under You and in the setup step. |
| `RelativeTime.since/day/due`, `TimeAgoText` | `RelativeTime.swift` | "10m", "4d", "Today", "Sat", "2 days late"; the year only when it is not this year. |
| `Avatar(name:photo:)` | `Avatar.swift` | The photo at 48 pt, or the monogram in New York on the soft accent. Puts the row's separator 14 pt past itself. |
| `FacePhoto(name:photo:)` | `FacePhoto.swift` | A face that fills its frame: the photo, or a 96 pt monogram at the top of the soft accent. For Review items and the card header. |
| `AdaptiveStack` | `AdaptiveStack.swift` | Side by side, stacked at accessibility text sizes. For row metadata and button pairs. |
| `AutonomySections(levels:choose:)` | `AutonomySections.swift` | One list section per job (Chat, Optimize profiles, Swipe) listing the four levels with `AutonomyLevel.summary`. The host loads the levels and saves the choice. Used by `AutopilotView` and the setup step. |
| `.autosave(value, saved:) { save }` | `Autosave.swift` | Saves a second after the last change and when the view goes away. Pass `value` as `saved` until loaded. Ignore errors from a cancelled save. |
| `GrowingField(label:prompt:text:)` | `GrowingField.swift` | A text field that grows, hides the keyboard on return and takes taps on its whole 44 pt row. `label` is read by VoiceOver. |
| `ErrorRow(text:retry:)` | `ErrorRow.swift` | A failed load or save next to what failed, in primary text with a red icon; tapping it retries. Borderless, so it can share a row with a field. |
| `StatusStrip(client:tab:)` | `StatusStrip.swift` | The status strip, as a modifier on the `TabView`: its bottom accessory while `GET /status` has a message. Only `MainTabView` uses it. |
| `\.motionReduced` | `Motion.swift` | True with Reduce Motion or Low Power Mode on. Read it before any spring, ring or color field and use a fade instead. |

Type: SF Pro text styles. New York (`.fontDesign(.serif)`) only for explanations, empty states, setup and monograms.

## Editing screens

`VoiceView` (the voice questionnaire, rendered from the server's `questions`) and `PreferencesView` follow one pattern: load once, keep the server's copy as `saved`, `.autosave` the edited copy, and show `ErrorRow` under each field whose value differs from `saved` after a failed save. Lists dismiss the keyboard on scroll (`.scrollDismissesKeyboard(.immediately)`). Push either one; they set their own title and toolbar.

## Card rows

Every `Card` carries its card summary (see "Cards and messages"): `stageChangedAt`, `stalled`, `lastMessage` (`LastMessage`: sender, body, sent time), `hot`, `pendingDraft`, `leadPhotoUrl`. A row reads only these, never `/queue`. `CardRow` (`Components/CardRow.swift`) is the A3 row: `Avatar` with the lead photo, the name with `TimeAgoText(date: card.lastActivity)` at the trailing edge (the last message, or the last stage change), "Chatting · Tinder", then the Hot, Stalled and Overdue badges. Name and time, and caption and badges, are each an `AdaptiveStack`, so they stack at accessibility sizes.
`CardRow(card:) { status }` puts a status line between the name and the caption; `CardRow(card:)` has none.

## Pipeline

`PipelineView` renders the groups `GET /pipeline` sends (`client.pipeline()`, `[PipelineGroup]`), in the server's order. Each card also carries `pipelineGroup`, `reason`, `handoverTrigger` and `autopilotActivity`, the server's codes, kept as strings so a newer server's code does not break decoding.

- **Headers** are rows: the group's title, its count and a chevron, 44 pt, a tap collapses the group. Waiting for you is in the accent. Archived starts collapsed. A search opens every group.
- **Status line**: `Card.pipelineStatus(now:calendar:)` (in `PipelineView.swift`) words the codes, one source per group: the reason for Waiting for you, the activity for Handled by autopilot, then the card's `topic` when it has one ("sent 4d ago, no reply yet · talking museums"), "You wrote 3h ago" for Waiting for them, the next action and its day for Texting off-app, else "Date rated 5/5" or "No next action". An unknown code shows no line. `AIMarker(.draft)` goes with "Reply ready in Review", `AIMarker(.autopilot)` with every Handled by autopilot row. "Rate the date" is a 44 pt button that opens `DateRatingSheet`.
- **Motion**: headers and cards are one `ForEach`, so a card whose group changed is the same row and moves there with a spring on reload. With `motionReduced` the card's row id includes its group, so it fades out and in instead.
- Returning from a card, adding one and rating reload the Pipeline. Screenshots: `docs/design/screenshots/redesign/t52-pipeline-*.png`.

## Review

`Screens/QueueView.swift` renders `GET /queue` (see "Review queue") in a `ScrollView`, hot leads first, with pull to refresh. Its state is `ReviewQueue` (`ios/DatingCRM/ReviewQueue.swift`, `@Observable`): `items`, `load()`, `remove(item)` for an item the server no longer holds, and `dismiss(item)` / `undo(item)`.

- **Faces in glass** (ADR 0009, the one place glass sits on content): `PhotoCard` puts `FacePhoto` behind the item and the plate on Liquid Glass over its lower part, 200 pt below the top. The glass is on the plate's background, not its content (glass turns the black capsule grey), under a 72% fill of the system background, so plate text is `.primary` only; grey text and the AI marker go on an `Inset` (solid background). The Hot badge sits on the soft accent.
- **Every item:** `ItemHeader` (the name, a `NavigationLink(value: card)` that opens `CardDetailView`, and the Hot badge), then per kind: `DraftItem` ("Reply on Tinder" and the time of the answered message, the quote, the draft editable in place under the AI draft marker, Dismiss and Send or Copy), `CopiedDraftItem` ("Copied for Hinge, not sent yet", the text, Clear and Copy again), `HandoverItem` (why autopilot stopped, from the trigger codes in `HandoverItem.reason`, the quote, each suggested reply under AI suggests with Copy, Hand back and Take over), `PaidItemCard` (the item and its cost, the reason, a link to the profile, Decline and Approve). The profile opens in `CandidateProfile`, a sheet with the candidate's photos and bio from `GET /swipes`.
- **Dismiss with Undo:** `dismiss(item)` takes the draft out at once and calls `POST /drafts/{id}/dismiss` only after the undo window (5 s, the toast's time). Undo puts it back where it was and the server never hears of it; a reload meanwhile does not bring it back. A failed dismissal reloads, so the draft returns with the error.
- **Send or Copy** (ADR 0003): `DraftItem` offers Send when `draft.sendable`, else Copy. Either first saves an edit. Send calls `client.sendDraft(draftID:)` and `review.remove(item)`. Copy puts the text on the clipboard, calls `client.copy(draftID:)`, shows the toast "Copied. Paste it in Hinge." (`QueueItem.datingApp`, private to `QueueView.swift`) and reloads, so the item comes back as `copied_draft`.
- **Copied draft:** Copy again only puts the text on the clipboard, with the same toast. Clear is `review.dismiss(item)` with an Undo toast, like Dismiss. The item leaves on the next load once the user's message shows up in the chat.
- **Denies being AI:** `Draft.deniesAI` (`guardrail` holds `denies_ai`). Until the user edits the text, `DraftItem` shows why ("It says you're not an AI. Edit it before you send it.") and offers neither Send nor Copy; an edit the server still flags shows the reason again. A copied draft that denies being AI (a migrated v1 draft) offers Clear only.
- **A new action** (Retry, #57) goes in `DraftItem` or a view next to it; one that ends the item calls `review.remove(item)`, one with Undo follows `dismiss`/`undo`. A new item kind gets its own view next to `DraftItem` and a branch in `QueueView`'s `ForEach`, which branches on `item.kind`; kinds the app does not know are skipped.

## Connected apps

`ConnectedAppsView(client:)` lists each dating app from `client.connectedApps()` (`GET /connectors`, see "Sync") with its `ConnectorState`: Connected, broken with its alert and when it came (the alert line in the accent, since it waits on the user), Copilot only, Not connected, or No connector (Hinge, Bumble: the app drafts and the user copies). Connect or Reconnect opens `ConnectAppSheet(client:app:onConnected:)`, which shows `ConnectAppSheet.steps[app]` (Tinder's say a computer is needed) and a secure field for the session token, and calls `client.connect(app:token:)`. Copilot only asks first, then calls `client.chooseCopilotOnly(app:)`. The setup step can push `ConnectedAppsView`; anything that offers Reconnect can present `ConnectAppSheet` alone.

## Calendar

`CalendarView(client:)` shows whether Google Calendar is connected (`client.calendarConnected()`, `GET /calendar`, see "Google Calendar holds") with Connect, or Reconnect once connected. Connect gets Google's consent page from `client.calendarConsentURL()` (`GET /calendar/connect`) and opens it in an ephemeral `ASWebAuthenticationSession` that waits for the `datingcrm` scheme; the server's callback sends it there. The view then asks the server again and shows a toast, or a plain line when it is still not connected: Google refused, the user closed the page, or the server answered `503` (no Google OAuth client set up). The session is UIKit's, not SwiftUI's `webAuthenticationSession`, which failed on the simulator with `presentationContextNotProvided`. The setup step can push `CalendarView` as is.

## API dates

`APIClient` decodes a plain day (`2026-12-01`, local midnight) or a full timestamp (`2026-11-20T10:00:00.123456Z` or with an offset). It encodes plain days only. `Message.sentAt` is the first timestamp the app reads.

## Simulator checks

Besides the Debug sign-in (`DCRM_SERVER`, `DCRM_TOKEN`) and `DCRM_TAB`, `DCRM_OPEN=voice`, `preferences`, `connected-apps`, `calendar` or `swipe-layout` pushes that screen under You on launch: `SIMCTL_CHILD_DCRM_TAB=you SIMCTL_CHILD_DCRM_OPEN=voice xcrun simctl launch …`. `DCRM_SETUP=1` opens setup instead of the tabs, or on one step with its name (`DCRM_SETUP=voice`; see "Setup").

## Limits

- The Review badge is the system red, not the accent: `UITabBarItem.appearance().badgeColor` has no effect on the SwiftUI `TabView`. It updates when Today loads, not when Review clears an item.
- Not verified on screen: typing, autosave, the save error under a field and Edit on Voice and Preferences (screenshots only, no taps).
- Not verified on screen: the toast (Review's Dismiss and Swipe's Pass and Like show one, but nothing was tapped) and VoiceOver reading the AI marker and badges. Review's buttons, the card link and the profile sheet were not tapped either: screenshots only.
- Error text is still system red, under 4.5:1 on white, outside `ErrorRow`. Settings is still a grey grouped form until its ticket.
