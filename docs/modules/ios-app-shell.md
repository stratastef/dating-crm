# iOS app shell and shared components

The signed-in app is `MainTabView` (`ios/DatingCRM/Screens/MainTabView.swift`): a five-tab `TabView` that opens on Today (ADR 0005). Each tab owns its `NavigationStack`, except Pipeline, whose `PipelineView` keeps its own for push taps. iOS 26 is the minimum (ADR 0002).

| Tab | Shows now |
| --- | --- |
| Today | `TodayView` (see "Today"). Tapping the review count switches to Review. |
| Review | `QueueView`: the review queue as faces in glass (see "Review queue", On the phone). The tab's badge is the review count from Today's last load. |
| Pipeline | `PipelineView`: `GET /pipeline` grouped by who acts next (see "Pipeline", On the phone). A tapped push switches to this tab and opens the card. Search (minimized to a toolbar button) filters the loaded cards by name and opens every group; the plus button opens `NewCardSheet` to add a card by hand. |
| Swipe | `SwipeView`: the Off state, one at a time or the list, as the Swipe layout says (see "Swipe copilot", On the phone) |
| You | `YouView`: the Dashboard headline (`DashboardHeadline`, links to `DashboardView`), Autopilot (`AutopilotView`), Preferences, Swipe layout (`SwipeLayoutSection`), Connected apps (`ConnectedAppsView`), Calendar (`CalendarView`), Profile (Photos, Bios and prompts, Voice), Settings (Notifications `NotificationsView`, Privacy `PrivacyView`, Activity log `ActivityLogView`, Find and purge `PurgeView`), Sign out, which asks first. If `POST /sign-out` fails, the phone stays signed in and an `ErrorRow` under Sign out says so (tap to try again) |

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
| `DraftComposer(client:card:toast:needsVoice:reload:sent:)` | `DraftComposer.swift` | The card's draft docked at the bottom of its chat (see "Cards and messages", On the phone). |
| `SuggestedSendTime(draft:)` | `SuggestedSendTime.swift` | "Best sent around 20:15 · reason" for the user's draft while its send time is ahead; in the draft's `Inset`. Review and the composer. |
| `SendAtButton(at:action:)` | `SendAtButton.swift` | Send at: a secondary capsule "Send at 20:15" next to Send; VoiceOver reads "Send tomorrow at 07:05". |
| `HandoverBanner(client:card:handover:message:copied:changed:)` | `HandoverBanner.swift` | A card paused for handover, at the end of its chat (see "Cards and messages", On the phone). `HandoverBanner.reason(triggers)` words the trigger codes; Review uses it too. `HandoverBanner.words(_:)` is the one place a trigger code is put into words: `short` for the Pipeline's status line, `sentence` for the banner and Review. |
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
| `.tick`, `.tap`, `.press`, `.thud`, `.done`, `.alert`, `.fail`; `Haptic` and `.haptic(_:)` | `Haptics.swift` | The haptics vocabulary as `SensoryFeedback` names (see "Splash and haptics"). Where one view plays several, set `haptic = Haptic(.press)` in the action and put `.haptic(haptic)` on a view that stays on screen. |
| `HourRing.play()` | `HourRing.swift`, `HourRing.ahap` | The hour: the one Core Haptics pattern. Silent on hardware without haptics. |
| `Splash(ready:finish:)` | `Splash.swift` | The animated splash. Only `DatingCRMApp` uses it. |

Type: SF Pro text styles. New York (`.fontDesign(.serif)`) only for explanations, empty states, setup and monograms.

## Splash and haptics

Both follow `docs/brand/motion-and-haptics.md`.

- **Splash.** `DatingCRMApp` lays `Splash` over the app on a cold launch: its state lives as long as the process, so a resume never shows it. The generated launch screen stays blank. The ring draws, the dot lands, the wordmark rises (New York stands in for Newsreader, which the app does not bundle). It fades out once the dot has landed (920 ms) and Today's first load is over (`\.todayLoaded`), at 1.2 s at the latest, at once when there is no Today to wait for (sign-in, setup). With motion reduced: the finished mark and one 300 ms fade. No haptic.
- **Haptics.** `.sensoryFeedback` on the view that changes, played on the tap, not on the server's answer. Sign-in's done and fail follow the server. Done plays at the app root: sign-in is gone by then.

| Moment | Haptic | Where |
| --- | --- | --- |
| Sign-in code accepted / refused | done / fail | `DatingCRMApp` / `SignInView` |
| The user clears the last item in Review | done | `QueueView` (`ReviewQueue.cleared`; a load that comes back empty does not count) |
| Send, Send at, Retry, Send now, Take over, Like | press | Review items, `DraftComposer`, `HandoverBanner`, `SwipeView` |
| Copy, Dismiss, Clear, Hold, Hand back, Pass, Undo | tap | Review items, `DraftComposer`, `HandoverBanner`, `SwipeView`, the toast's Undo |
| A send fails as the user sends | fail | Review, `DraftComposer` |
| A handover fires while the card is open | alert | `CardDetailView`, not on the first load |
| A rating step, an autonomy level | tick | `RatingPicker`, `AutopilotView`, setup |
| Rate a date 4 or 5 / 1 to 3 | hour / tap | `DateRatingSheet` |
| A date set: the user picks Date set, or a reload of the open card shows it | hour | `CardDetailView` |
| A pause on / off, Resume | thud / press | `AutopilotView` (Pause all and each app), `StatusStrip` |
| Approve a paid item | thud | Review, Swipe's Super Like |
| The strip starts to say the AI budget is reached or a connector signed out | fail | `StatusStrip`, not on the first load |

Silent: the splash, scrolling, navigation, tab switches, the Pipeline's rows moving and anything autopilot does in the background. The Simulator plays no haptics, so each row is a manual check on an iPhone.

## Screens

A screen's own behaviour is in its feature's module doc, under "On the phone": Today, Review queue, Pipeline, Cards and messages (card detail, composer, rating sheet), Send timing, Swipe copilot, Dashboard, Autonomy and pause, Status strip, Setup, Sign-in, Sync (Connected apps), Google Calendar holds, Photos, Bios. This doc holds only what every screen shares.

## Editing screens

`VoiceView` (the voice questionnaire, rendered from the server's `questions`) and `PreferencesView` follow one pattern: load once, keep the server's copy as `saved`, `.autosave` the edited copy, and show `ErrorRow` under each field whose value differs from `saved` after a failed save. Lists dismiss the keyboard on scroll (`.scrollDismissesKeyboard(.immediately)`). Push either one; they set their own title and toolbar.

## Card rows

Every `Card` carries its card summary (see "Cards and messages"): `stageChangedAt`, `stalled`, `lastMessage` (`LastMessage`: sender, body, sent time), `hot`, `pendingDraft`, `leadPhotoUrl`. A row reads only these, never `/queue`. `CardRow` (`Components/CardRow.swift`) is the A3 row: `Avatar` with the lead photo, the name with `TimeAgoText(date: card.lastActivity)` at the trailing edge (the last message, or the last stage change), "Chatting · Tinder", then the Hot, Stalled and Overdue badges. Name and time, and caption and badges, are each an `AdaptiveStack`, so they stack at accessibility sizes.
`CardRow(card:) { status }` puts a status line between the name and the caption; `CardRow(card:)` has none.

## API dates

`APIClient` decodes a plain day (`2026-12-01`, local midnight) or a full timestamp (`2026-11-20T10:00:00.123456Z` or with an offset). It encodes plain days only. `Message.sentAt` is the first timestamp the app reads.

## Simulator checks

Besides the Debug sign-in (`DCRM_SERVER`, `DCRM_TOKEN`) and `DCRM_TAB`, `DCRM_OPEN=voice`, `dashboard`, `autopilot`, `preferences`, `connected-apps`, `calendar`, `swipe-layout`, `photos`, `bios`, `notifications`, `privacy`, `activity-log` or `purge` pushes that screen under You on launch: `SIMCTL_CHILD_DCRM_TAB=you SIMCTL_CHILD_DCRM_OPEN=voice xcrun simctl launch …`. `DCRM_CARD=7` with `DCRM_TAB=pipeline` opens that card on launch. `DCRM_SETUP=1` opens setup instead of the tabs, or on one step with its name (`DCRM_SETUP=voice`; see "Setup").

## Limits

- The Review badge is the system red, not the accent: `UITabBarItem.appearance().badgeColor` has no effect on the SwiftUI `TabView`. It updates when Today loads, not when Review clears an item.
- Not verified on screen: typing, autosave, the save error under a field and Edit on Voice and Preferences (screenshots only, no taps).
- Error text is still system red, under 4.5:1 on white, outside `ErrorRow`.

