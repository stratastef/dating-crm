# iOS app shell and shared components

The signed-in app is `MainTabView` (`ios/DatingCRM/Screens/MainTabView.swift`): a five-tab `TabView` that opens on Today (ADR 0005). Each tab owns its `NavigationStack`, except Pipeline, whose `PipelineView` keeps its own for push taps. iOS 26 is the minimum (ADR 0002).

| Tab | Shows now |
| --- | --- |
| Today | `TodayView` (see "Today"). Tapping the review count switches to Review. |
| Review | `QueueView`: the review queue as faces in glass (see "Review"). The tab's badge is the review count from Today's last load. |
| Pipeline | `PipelineView`: `GET /pipeline` grouped by who acts next (see "Pipeline" below). A tapped push switches to this tab and opens the card. Search (minimized to a toolbar button) filters the loaded cards by name and opens every group; the plus button opens `NewCardSheet` to add a card by hand. |
| Swipe | `SwipeView`: the Off state, one at a time or the list, as the Swipe layout says (see "Swipe copilot", On the phone) |
| You | `YouView`: the Dashboard headline (`DashboardHeadline`, links to `DashboardView`), Autopilot (`AutopilotView`), Preferences, Swipe layout (`SwipeLayoutSection`), Connected apps (`ConnectedAppsView`), Calendar (`CalendarView`), Profile (Photos, Bios and prompts, Voice), Settings (Notifications `NotificationsView`, Privacy `PrivacyView`, Activity log `ActivityLogView`, Find and purge `PurgeView`), Sign out, which asks first |

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
| `Toast.sending(to: name) { undo }` | `Toast.swift` | The user's Send: "Sending to Ada…" with Undo and an accent ring that drains over the 5 seconds the server holds the send, then "Sent to Ada". With motion reduced the ring fades instead. `undo` calls `client.undoSend(draftID:)` (`409`: too late). Review uses it; so does the card's composer. |
| `Ring(left:)` | `Ring.swift` | Time left as a 22 pt accent ring, full at 1, gone at 0. Hidden from VoiceOver: the text beside it says what it counts down to. `Toast.sending` and `PlannedRing` draw it. |
| `PlannedRing(draft:)` | `PlannedRing.swift` | A planned send's `Ring`, draining from `Draft.createdAt` to `Draft.sendAt`, redrawn every second by `TimelineView`. With motion reduced it stays where it was drawn. `PlannedRing.left(from:to:now:)` is the share left. |
| `Held(after:) { action }` | `Held.swift` | Runs the action after 5 seconds unless `undo()` comes first; `undo()` is false once it started. Pair it with a toast's Undo for what the server cannot take back (a swipe). |
| `SwipeLayoutSection(client:)` | `SwipeLayoutSection.swift` | The Swipe layout choice as one list section that loads and saves itself. Under You and in the setup step. |
| `RelativeTime.since/day/due/around`, `TimeAgoText` | `RelativeTime.swift` | "10m", "4d", "Today", "Sat", "2 days late"; the year only when it is not this year. `around` is a send time: "around 20:15", "tomorrow around 07:05". |
| `Avatar(name:photo:size:)` | `Avatar.swift` | The photo at 48 pt (`size` for smaller, such as 32 pt in a navigation bar), or the monogram in New York on the soft accent. Puts the row's separator 14 pt past itself. |
| `Inset { … }` | `Inset.swift` | A solid surface inside a glass plate or the composer, where grey text and the AI marker stay at 4.5:1. |
| `DraftComposer(client:card:toast:needsVoice:reload:sent:)` | `DraftComposer.swift` | The card's draft docked at the bottom of its chat (see "Card detail"). |
| `SuggestedSendTime(draft:)` | `SuggestedSendTime.swift` | "Best sent around 20:15 · reason" for the user's draft while its send time is ahead; in the draft's `Inset`. Review and the composer. |
| `SendAtButton(at:action:)` | `SendAtButton.swift` | Send at: a secondary capsule "Send at 20:15" next to Send; VoiceOver reads "Send tomorrow at 07:05". |
| `HandoverBanner(client:card:handover:message:copied:changed:)` | `HandoverBanner.swift` | A card paused for handover, at the end of its chat (see "Card detail"). `HandoverBanner.reason(triggers)` words the trigger codes; Review uses it too. |
| `FacePhoto(name:photo:)` | `FacePhoto.swift` | A face that fills its frame: the photo, or a 96 pt monogram at the top of the soft accent. For Review items and the card header. |
| `.blurredFace()` (`BlurredFace`) | `BlurredFace.swift` | Blur photos (ADR 0009): put it on a loaded face image, inside its clip. With the setting on, the face is blurred until tapped, and that tap reveals instead of reaching the row. `Avatar`, `FacePhoto` and Swipe's photos use it; a new face (the card header) uses one of those or this. The setting is the server's (`blur_photos`); the app keeps a copy in `@AppStorage(BlurredFace.key)`, which `MainTabView` refreshes on launch and `PrivacyView` on each change. |
| `AdaptiveStack` | `AdaptiveStack.swift` | Side by side, stacked at accessibility text sizes. For row metadata and button pairs. |
| `AutonomySections(levels:choose:)` | `AutonomySections.swift` | One list section per job (Chat, Optimize profiles, Swipe) listing the four levels with `AutonomyLevel.summary`. The host loads the levels and saves the choice. Used by `AutopilotView` and the setup step. |
| `.autosave(value, saved:) { save }` | `Autosave.swift` | Saves a second after the last change and when the view goes away. Pass `value` as `saved` until loaded. Ignore errors from a cancelled save. |
| `GrowingField(label:prompt:text:)` | `GrowingField.swift` | A text field that grows, hides the keyboard on return and takes taps on its whole 44 pt row. `label` is read by VoiceOver. |
| `RatingPicker(title:rating:)` | `RatingPicker.swift` | The date's rating as one list section: 1 to 5 as 44 pt rows, each with its anchor ("Good: I'd like another date"), 4 and 5 marked "Good date", the footer "Good = rated 4 or 5." `rating` is nil until chosen. The rating sheet and the card's Details use it. |
| `ErrorRow(text:retry:)` | `ErrorRow.swift` | A failed load or save next to what failed, in primary text with a red icon; tapping it retries. Borderless, so it can share a row with a field. |
| `StatusStrip(client:tab:)` | `StatusStrip.swift` | The status strip, as a modifier on the `TabView`: its bottom accessory while `GET /status` has a message. Only `MainTabView` uses it. |
| `\.motionReduced` | `Motion.swift` | True with Reduce Motion or Low Power Mode on. Read it before any spring, ring or color field and use a fade instead. |

Type: SF Pro text styles. New York (`.fontDesign(.serif)`) only for explanations, empty states, setup and monograms.

## Editing screens

`VoiceView` (the voice questionnaire, rendered from the server's `questions`) and `PreferencesView` follow one pattern: load once, keep the server's copy as `saved`, `.autosave` the edited copy, and show `ErrorRow` under each field whose value differs from `saved` after a failed save. Lists dismiss the keyboard on scroll (`.scrollDismissesKeyboard(.immediately)`). Push either one; they set their own title and toolbar.

## Profile

Under You, Profile holds what optimizes the user's own profiles: `PhotosView`, `BiosView` and `VoiceView`.

- **`PhotosView`**: the photos in the server's order; the first is labeled "Lead photo", the others show Claude's reason. Edit (or a drag) reorders them and sends the whole order (`PUT /photos/order`); a failed save puts the old order back. Swipe or Edit deletes one after a confirmation (`DELETE /photos/{id}`). An edit on offer shows under AI suggests, the original and the edited preview side by side at every text size, then Accept edit and Keep original.
- **`BiosView`**: a segmented picker per dating app (`tinder`, `hinge`, `bumble`, the server's `DATING_APPS`), the accepted bio and prompts from `GET /bios/{app}` as fields, and "Rewrite in my voice". The rewrite shows under AI suggests, selectable for copying, with Accept (`PUT /bios/{app}`) and Rewrite again. A `409` (no style profile yet) shows a link to `VoiceView`. Nothing autosaves: what the user types is only sent to be rewritten, so leaving or switching app drops it. Prompts show in the order typed, or by their text after a load (`Bio.prompts` is a dictionary).

## Card rows

Every `Card` carries its card summary (see "Cards and messages"): `stageChangedAt`, `stalled`, `lastMessage` (`LastMessage`: sender, body, sent time), `hot`, `pendingDraft`, `leadPhotoUrl`. A row reads only these, never `/queue`. `CardRow` (`Components/CardRow.swift`) is the A3 row: `Avatar` with the lead photo, the name with `TimeAgoText(date: card.lastActivity)` at the trailing edge (the last message, or the last stage change), "Chatting · Tinder", then the Hot, Stalled and Overdue badges. Name and time, and caption and badges, are each an `AdaptiveStack`, so they stack at accessibility sizes.
`CardRow(card:) { status }` puts a status line between the name and the caption; `CardRow(card:)` has none.

## Pipeline

`PipelineView` renders the groups `GET /pipeline` sends (`client.pipeline()`, `[PipelineGroup]`), in the server's order. Each card also carries `pipelineGroup`, `reason`, `handoverTrigger` and `autopilotActivity`, the server's codes, kept as strings so a newer server's code does not break decoding.

- **Headers** are rows: the group's title, its count and a chevron, 44 pt, a tap collapses the group. Waiting for you is in the accent. Archived starts collapsed. A search opens every group.
- **Status line**: `Card.pipelineStatus(now:calendar:)` (in `PipelineView.swift`) words the codes, one source per group: the reason for Waiting for you, the activity for Handled by autopilot, then the card's `topic` when it has one ("sent 4d ago, no reply yet · talking museums"), "You wrote 3h ago" for Waiting for them ("Your reply goes out at 20:15" with a scheduled send, `card.scheduledSend`), the next action and its day for Texting off-app, else "Date rated 5/5" or "No next action". A planned send (`planned`) says when and why instead of the topic: "replies around 20:15 · they take their time", from `card.plannedSend` (`sendAt`, `timingReason`); with no reason it ends with the topic. A planned opener (`plannedSend.kind` `opener`) says "sends an opener around 17:40"; before it is written, "writing an opener". An unknown code shows no line. `AIMarker(.draft)` goes with "Reply ready in Review", `AIMarker(.autopilot)` with every Handled by autopilot row; a planned send's row puts its `PlannedRing` before the marker. "Rate the date" is a 44 pt button that opens `DateRatingSheet`.
- **Motion**: headers and cards are one `ForEach`, so a card whose group changed is the same row and moves there with a spring on reload. With `motionReduced` the card's row id includes its group, so it fades out and in instead.
- Returning from a card, adding one and rating reload the Pipeline. Screenshots: `docs/design/screenshots/redesign/t52-pipeline-*.png`, with planned sends `t71-pipeline-*.png`, with openers `t73-pipeline-*.png`.

## Send timing

- **The card's planned send** docks in the composer (see "Card detail"), and its Pipeline row has the same `PlannedRing`. Screenshots: `t72-card-*.png`, `t72-pipeline-*.png`.
- **Night window:** a section of `AutopilotView` under Pause, two hour pickers (From, Until) loaded with `client.settings()` and saved together with `client.setNightWindow(start:end:)` (`UserSettings.nightWindowStart/End`, hours 0–23). Screenshots: `t71-autopilot-*.png`.
- `Draft.sendAt` and `Draft.timingReason` are optional, so drafts from an older server decode.

## Card detail

`CardDetailView(client:card:onSaved:)` (`Screens/CardDetailView.swift`) is one card, opened from Today, Review, the Pipeline and a push. It loads the card (`GET /cards/{id}`) and its messages on appear, keeping Details edits not yet saved. `onSaved` runs after anything that can move the card in a list.

- **Header**: `FacePhoto` 340 pt high with the name and "Chatting on Tinder, matched 3d ago" (`Card.createdAt`) on a glass plate, the plate's fill as on Review's. It is the first thing in both tabs. Scrolled past it, the navigation bar shows the face (`Avatar`, 32 pt) and name (`onScrollGeometryChange`).
- **Tabs**: Chat and Details, a segmented picker in a `safeAreaBar` at the top. The card opens on Chat when `Stage.chatsInApp` (Matched, Chatting), else on Details.
- **Chat**: the messages as bubbles, the match's on the left on the fill, the user's on the right in the label color. A time ("Yesterday 7:24 PM") heads the first message and each one an hour or more after the one before; the last message says how long ago it was sent. `AIMarker(.autopilot)` sits under each message with `sentByAutopilot`. The chat opens on the newest message (`ScrollPosition`, scrolled to the bottom after each load).
- **Handover banner** (`HandoverBanner`): when `card.handover` is set, at the end of the chat, so it scrolls at large text sizes. Pending: why autopilot stopped (`reason(_:)` on the trigger codes of the newest match message with a `handover` hit), that message quoted, each suggested reply under AI suggests with Copy, then Hand back and Take over. Taken over: one line and Hand back. Either reloads the card.
- **Composer** (`DraftComposer`, in a bottom `safeAreaBar`, glass over a 72% fill): it docks `card.plannedSend` first, then `card.scheduledSend`, else `card.drafts?.first` by `Draft.status`.
  - Planned send: `PlannedRing` and "Replies around 20:15", the timing reason, the text under Autopilot in an `Inset` (it scrolls above the buttons when it does not fit, at the largest text sizes), then Hold and Send now (only if `sendable`). Send now calls `client.sendNow`, toasts "Sending to Ada…" (no Undo: it goes at once) and calls `sent`. Hold calls `client.hold`, toasts "Held. It waits in Review." and reloads, so the draft docks again as pending. A `409` on either reloads and says why.
  - `pending`: the text editable in an `Inset` under AI draft, then Send if `sendable`, else Copy. Either saves an edit first. A draft that denies being AI says so and offers neither until edited.
  - `copied`: "Copied, not sent yet", the text, Clear (hidden at once, `POST /drafts/{id}/dismiss` after the toast's 5 seconds unless Undo, through `Held`) and Copy again (clipboard only).
  - `failed`: the warning Review shows, the text editable, Copy and Retry (Retry only if `sendable`).
  - No draft: Write draft in Matched and Chatting (`POST /cards/{id}/drafts`, then a reload); nothing from Number swapped on. A `409` (no style profile yet) sets `needsVoice`, and the card pushes `VoiceView`.
  - Send and Retry call `client.sendDraft`, show `Toast.sending` (Undo: `client.undoSend`, then a reload; `409` says it is too late) and call `sent`: the card reloads at once (the draft leaves the dock), then every 3 seconds, at most 4 times, until a new message is in the chat. Copy calls `client.copy`, toasts "Copied. Paste it in Hinge." and reloads, so the draft docks again as copied.
  - **Suggested send time:** `pending` and `copied` show `SuggestedSendTime` in the `Inset` ("Best sent around 20:15 · she's on a roll", from `sendAt` and `timingReason`; nothing once the time has passed, `Draft.suggestedSendAt`). A pending draft the app can send gets `SendAtButton` ("Send at 20:15", VoiceOver adds the day) next to Send: `client.sendDraft(draftID:at:)`, a toast "Goes to Ada at 20:15" with no Undo, and a reload.
  - **Scheduled send** (`card.scheduledSend`), docked before any draft: "Goes out at 20:15", the text, and Cancel (`client.unschedule(draftID:)`, then a reload, so it docks as pending again; `409`: "Too late to cancel the message to Ada."). Screenshots: `t74-card-*.png`, and Review's `t74-review-*.png`.
- **Details**: a plain list under the header: Stage; Next action (a labeled `GrowingField`) with the Due date toggle and day; Notes; for a rated card or a Dated one, the date's rating (`RatingPicker`, nothing selected until rated) and its note; then the match read (`ReadSection`).
  - Edits save as the user makes them: `.autosave` on the whole card compares `Edits` (stage, notes, next action, due date, rating, note), not the whole card, a second after the last change and when the card goes away (popping it, or pushing `VoiceView`). Switching to Chat keeps the debounce running. A load or a save's answer keeps edits the server does not have yet (`take(_:)`). A failed save shows `ErrorRow` under each field whose edit is not saved; tapping it saves again.
  - Reaching Dated unrated opens the rating sheet; "Not now" leaves the rating on Details.
  - Match read: each inference's kind, its `confidenceWord` (Sure, Likely, Guess; "Corrected by you" once corrected), the value and "Evidence: …" in `.subheadline`. Kind and word stack at accessibility sizes. A tap corrects it in an alert (`PATCH /inferences/{id}`).
- **Rating sheet** (`DateRatingSheet(name:onRated:)`, `Screens/DateRatingSheet.swift`): one sheet for the card, Today's dates to rate and the Pipeline's "Rate the date" rows. `RatingPicker` with nothing selected, a note, "Not now" and Save, which waits for a rating. The host saves with `client.update` and no stage change.
- Screenshots: `docs/design/screenshots/redesign/t59-card-*.png` (Chat), `t60-*.png` (Details, rating sheet), `t72-card-*.png` (planned send).

## Review

`Screens/QueueView.swift` renders `GET /queue` (see "Review queue") in a `ScrollView`, hot leads first, with pull to refresh. Its state is `ReviewQueue` (`ios/DatingCRM/ReviewQueue.swift`, `@Observable`): `items`, `load()`, `remove(item)` for an item the server no longer holds, and `dismiss(item)` / `undo(item)`.

- **Faces in glass** (ADR 0009, the one place glass sits on content): `PhotoCard` puts `FacePhoto` behind the item and the plate on Liquid Glass over its lower part, 200 pt below the top. The glass is on the plate's background, not its content (glass turns the black capsule grey), under a 72% fill of the system background, so plate text is `.primary` only; grey text and the AI marker go on an `Inset` (solid background). The Hot badge sits on the soft accent.
- **Every item:** `ItemHeader` (the name, a `NavigationLink(value: card)` that opens `CardDetailView`, and the Hot badge), then per kind: `DraftItem` ("Reply on Tinder" and the time of the answered message, the quote, the draft editable in place under the AI draft marker with its `SuggestedSendTime`, Dismiss and Send or Copy, and Send at next to Send), `CopiedDraftItem` ("Copied for Hinge, not sent yet", the text and its `SuggestedSendTime`, Clear and Copy again), `HandoverItem` (why autopilot stopped, from the trigger codes in `HandoverBanner.reason`, the quote, each suggested reply under AI suggests with Copy, Hand back and Take over), `PaidItemCard` (the item and its cost, the reason, a link to the profile, Decline and Approve). The profile opens in `CandidateProfile`, a sheet with the candidate's photos and bio from `GET /swipes`.
- **Dismiss with Undo:** `dismiss(item)` takes the draft out at once and calls `POST /drafts/{id}/dismiss` only after the undo window (5 s, the toast's time). Undo puts it back where it was and the server never hears of it; a reload meanwhile does not bring it back. A failed dismissal reloads, so the draft returns with the error.
- **Send or Copy** (ADR 0003): `DraftItem` offers Send when `draft.sendable`, else Copy. Either first saves an edit. Send calls `client.sendDraft(draftID:)`, then `QueueView` removes the item and shows `Toast.sending`. Its Undo is `review.undoSend(item)`: `POST /drafts/{id}/undo-send`, then a reload, so the draft comes back as the server has it, pending and editable; too late (`409`), it reloads and says "Too late to undo the message to Ada." Copy puts the text on the clipboard, calls `client.copy(draftID:)`, shows the toast "Copied. Paste it in Hinge." (`QueueItem.datingApp`, private to `QueueView.swift`) and reloads, so the item comes back as `copied_draft`.
- **Copied draft:** Copy again only puts the text on the clipboard, with the same toast. Clear is `review.dismiss(item)` with an Undo toast, like Dismiss. The item leaves on the next load once the user's message shows up in the chat.
- **Send at:** a pending draft the app can send, whose suggested send time is ahead, shows `SendAtButton` between Dismiss and Send; where the three do not fit in a row (larger text), Send at goes above them (`ViewThatFits`). It calls `client.sendDraft(draftID:at:)`; `QueueView` removes the item and toasts "Goes to Ada at 20:15" with Undo (`review.undoSend(item)`) but no ring, since the server holds no Undo wait. Later, the card's composer shows it with Cancel. Review has no scheduled-send item: it holds what waits for the user.
- **Denies being AI:** `Draft.deniesAI` (`guardrail` holds `denies_ai`). Until the user edits the text, `DraftItem` shows why ("It says you're not an AI. Edit it before you send it.") and offers neither Send nor Copy; an edit the server still flags shows the reason again. A copied draft that denies being AI (a migrated v1 draft) offers Clear only.
- **Failed send** (`failed_send`): `DraftItem` again, with "Sending failed. It may still have reached Tinder, so check the chat before you send it again." and Copy and Retry instead of Dismiss and Send. Retry is Send (`POST /drafts/{id}/send`), with the same toast and Undo. A failed send the app cannot send now offers Copy only.
- **A new action** goes in `DraftItem` or a view next to it; one that ends the item calls `review.remove(item)`, one with Undo follows `dismiss`/`undo`. A new item kind gets its own view next to `DraftItem` and a branch in `QueueView`'s `ForEach`, which branches on `item.kind`; kinds the app does not know are skipped.

## Connected apps

`ConnectedAppsView(client:)` lists each dating app from `client.connectedApps()` (`GET /connectors`, see "Sync") with its `ConnectorState`: Connected, broken with its alert and when it came (the alert line in the accent, since it waits on the user), Copilot only, Not connected, or No connector (Hinge, Bumble: the app drafts and the user copies). Connect or Reconnect opens `ConnectAppSheet(client:app:onConnected:)`, which shows `ConnectAppSheet.steps[app]` (Tinder's say a computer is needed) and a secure field for the session token, and calls `client.connect(app:token:)`. Copilot only asks first, then calls `client.chooseCopilotOnly(app:)`. The setup step can push `ConnectedAppsView`; anything that offers Reconnect can present `ConnectAppSheet` alone.

## Calendar

`CalendarView(client:)` shows whether Google Calendar is connected (`client.calendarConnected()`, `GET /calendar`, see "Google Calendar holds") with Connect, or Reconnect once connected. Connect gets Google's consent page from `client.calendarConsentURL()` (`GET /calendar/connect`) and opens it in an ephemeral `ASWebAuthenticationSession` that waits for the `datingcrm` scheme; the server's callback sends it there. The view then asks the server again and shows a toast, or a plain line when it is still not connected: Google refused, the user closed the page, or the server answered `503` (no Google OAuth client set up). The session is UIKit's, not SwiftUI's `webAuthenticationSession`, which failed on the simulator with `presentationContextNotProvided`. The setup step can push `CalendarView` as is.

## API dates

`APIClient` decodes a plain day (`2026-12-01`, local midnight) or a full timestamp (`2026-11-20T10:00:00.123456Z` or with an offset). It encodes plain days only. `Message.sentAt` is the first timestamp the app reads.

## Simulator checks

Besides the Debug sign-in (`DCRM_SERVER`, `DCRM_TOKEN`) and `DCRM_TAB`, `DCRM_OPEN=voice`, `dashboard`, `autopilot`, `preferences`, `connected-apps`, `calendar`, `swipe-layout`, `photos`, `bios`, `notifications`, `privacy`, `activity-log` or `purge` pushes that screen under You on launch: `SIMCTL_CHILD_DCRM_TAB=you SIMCTL_CHILD_DCRM_OPEN=voice xcrun simctl launch …`. `DCRM_CARD=7` with `DCRM_TAB=pipeline` opens that card on launch. `DCRM_SETUP=1` opens setup instead of the tabs, or on one step with its name (`DCRM_SETUP=voice`; see "Setup").

## Limits

- The Review badge is the system red, not the accent: `UITabBarItem.appearance().badgeColor` has no effect on the SwiftUI `TabView`. It updates when Today loads, not when Review clears an item.
- Not verified on screen: typing, autosave, the save error under a field and Edit on Voice and Preferences (screenshots only, no taps).
- Not verified on screen: reorder, delete, Accept edit and Keep original on Photos; Rewrite, Accept and the Voice link on Bios. The rewrite needs Claude and a tap, so it was never shown.
- Not verified on screen: the toast (Review's Dismiss and Swipe's Pass and Like show one, but nothing was tapped) and VoiceOver reading the AI marker and badges. Review's buttons, the card link and the profile sheet were not tapped either: screenshots only.
- Not verified on screen: anything tapped on the card (Send, Undo, Copy, Clear, Retry, Write draft, the voice questionnaire push, Take over, Hand back, switching tabs, scrolling the header back in); screenshots only. At the largest text size the composer takes most of the screen.
- Error text is still system red, under 4.5:1 on white, outside `ErrorRow`.
