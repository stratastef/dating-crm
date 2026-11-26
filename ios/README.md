# Dating CRM for iOS

The SwiftUI client for the API in the repo root. It builds with Xcode 27 locally and Xcode 26.6 in CI (pinned in `.github/workflows/ci.yml`), for an iOS 26 or later simulator or device. Code must build on both: Xcode 26.6 rejects some code Xcode 27 accepts, so a green local run is not a green `ios` job.

## Layout

| Path | Purpose |
| --- | --- |
| `DatingCRM.xcodeproj` | The app target, the share extension target `DatingCRMShare` and one unit test target. |
| `DatingCRM/DatingCRMApp.swift` | App entry: shows `SignInView` or `MainTabView` (the five tabs), depending on `Session`. |
| `DatingCRM/Session.swift` | Sign-in state: phone number sign-in, developer sign-in, sign-out. Keeps the server URL in `UserDefaults` and this device's API token in the Keychain, where the share extension reads both. |
| `DatingCRM/ForegroundTimer.swift` | Measures each foreground stretch; the app entry reports it with `POST /time` when the app leaves the foreground. |
| `DatingCRM/Push.swift` | `Push` (device token, tapped card) and `AppDelegate`, which receives both from UIKit. |
| `DatingCRM.entitlements` | The push notification entitlement. |
| `DatingCRM/API/APIClient.swift` | Every call to the server. |
| `DatingCRM/API/Models.swift` | The JSON the server sends. Cards: `Stage`, `Handover`, `Card`, `PipelineGroup`, `LastMessage`, `Message`, `Draft`, `Inference`. Today and Review: `Today`, `SetupSummary`, `SetupStep`, `ReviewSummary`, `TodayItem`, `QueueItem`, `QuotedMessage`, `PaidItem`. Swipe: `Swipe`, `SwipeCandidate`, `SwipeLayout`, `SwipeLimits`. Autopilot and status: `Pauses`, `AutonomyLevel`, `Budget`, `StatusMessage`, `ConnectedApp`, `ConnectorState`, `ConnectorAlert`. You: `Dashboard`, `DashboardWeek`, `UserSettings`, `ActivityEntry`, `PurgeConfirmation`, `Preferences`, `Voice`, `ProfilePhoto`, `PhotoEdit`, `Bio`. |
| `DatingCRM/ReviewQueue.swift` | `ReviewQueue`: the review queue as Review shows it. A dismissal reaches the server only once its Undo is gone; `undoSend` takes a send back. |
| `DatingCRM/Components/` | Shared views and helpers, one type per file: the A3 look (`Palette`: colors and button styles; `AIMarker`, `Badge`, `Toast`, `Avatar`, `FacePhoto`, `BlurredFace`, `RelativeTime`, `AdaptiveStack`, `Motion`, `Ring`, `ErrorRow`, `Inset`, `GrowingField`), card parts (`CardRow`, `DraftComposer`, `HandoverBanner`, `Held`, `PlannedRing`, `SuggestedSendTime`, `SendAtButton`, `RatingPicker`, `Autosave`), and pieces of You and Today (`StatusStrip`, `DashboardHeadline`, `AutonomySections`, `SwipeLayoutSection`). See `docs/modules/ios-app-shell.md`. |
| `DatingCRM/Screens/` | One file per screen. `PhotosView` uploads photos from the photo library as JPEG, ranks, reorders and deletes them, labels the first "Lead photo", and shows each offered edit next to the original to accept or reject. The server makes every preview from the uploaded pixels. |
| `DatingCRM/ScreenshotImport.swift` | Uploads a shared screenshot and holds the draft or error the share extension shows. |
| `DatingCRMShare/` | The share extension: `ShareViewController` takes the picture from the share sheet, `ScreenshotImportView` shows the result. |
| `ShareInfo.plist`, `DatingCRMShare.entitlements` | The share extension's Info.plist keys and entitlements. |
| `DatingCRMTests/` | Unit tests (Swift Testing). `StubServer` stands in for the server. |
| `Info.plist` | Only the keys that build settings cannot express. The rest of the Info.plist is generated. |

All targets use folders that Xcode keeps in sync with the disk. A file you add under `DatingCRM/`, `DatingCRMShare/` or `DatingCRMTests/` is part of that target with no change to `project.pbxproj`, so branches that add files do not conflict on the project file. Do not put a file meant for one target in the other folder.

The share extension also compiles four files from `DatingCRM/`: `API/APIClient.swift`, `API/Models.swift`, `Session.swift` and `ScreenshotImport.swift`. They are listed in `project.pbxproj` under `PBXFileSystemSynchronizedBuildFileExceptionSet`. If one of them starts to use a type from another file, the extension stops building: move the type into one of the four, or add its file to that list (in Xcode: the file's Target Membership). These files may only use APIs allowed in app extensions, so no `UIApplication.shared`.

## Build and test

From the repo root:

```sh
xcodebuild build -project ios/DatingCRM.xcodeproj -scheme DatingCRM -destination 'platform=iOS Simulator,name=iPhone 18 Pro'
xcodebuild test  -project ios/DatingCRM.xcodeproj -scheme DatingCRM -destination 'platform=iOS Simulator,name=iPhone 18 Pro'
```

`scripts/ios-test` runs the tests on a simulator and build folder of the worktree's own and deletes both afterwards, so worktrees testing in parallel never share either. It prints the summary, or the errors and the log's path.

`xcrun simctl list devices available` lists the simulator names you can use. The tests need no server.

To run on your own iPhone, open the project in Xcode, pick your team under Signing & Capabilities and change the bundle identifier `com.datingcrm.app` to one you own.

## Sign in

`SignInView` asks for the phone number, then for the sign-in code the server texts to it ("your Dating CRM code"). A new code can be asked for 30 seconds after the last. A refusal (wrong or expired code, too many tries, no account for the number) shows in plain words under the field. See `docs/modules/sign-in.md` for the routes.

- The server is `ServerURL` in `Info.plist`, `http://localhost:8000` for now. Set it to the production server before a TestFlight build.
- In local development (`SMS_PROVIDER=log`, the `compose.yaml` default) the server writes the code to its log (`SMS to +1…: 123456 is your Dating CRM code`). Running the API with `uv run uvicorn`, set `SMS_PROVIDER=log` yourself: unset, code requests fail with `503`. Give your account a phone number first: `uv run python -m app.sign_in you@example.com +491701234567`.
- Developer sign-in: a two-second press on the "Dating CRM" title opens a sheet for a server URL and an API token from `uv run python -m app.auth you@example.com`. The app checks them with one `GET /cards` before it keeps them.
- Sign out sits under You and asks first. It revokes this device's token on the server (`POST /sign-out`), which also stops this phone's pushes, then forgets the session. If the server cannot be reached, the phone stays signed in and says so next to Sign out.

A server on `localhost` or your local network may use plain `http`. Any other server needs `https`.

### Scripted simulator checks

Debug builds sign in from the launch environment, store nothing and skip the push permission alert. `DCRM_TAB` opens a tab other than Today (`review`, `pipeline`, `swipe`, `you`):

```sh
SIMCTL_CHILD_DCRM_SERVER=http://localhost:8047 SIMCTL_CHILD_DCRM_TOKEN=<token> SIMCTL_CHILD_DCRM_TAB=review \
  xcrun simctl launch <udid> com.datingcrm.app
```

`DCRM_SERVER` without a token points the phone number sign-in at that server. `DCRM_PHONE=+15555550100` opens the code step for that number without sending a code.

## Share a screenshot

In any dating app, take a screenshot of a chat or profile, tap Share and pick Dating CRM. The extension sends the picture to `POST /screenshots` as JPEG, the server reads it into the match's card, and the extension shows the draft with a Copy button. See "Screenshot import" in the root `README.md`.

The extension uses the session of the app: the server URL from the defaults of a shared App Group, the token from a shared Keychain access group. Before it runs on a device, set these in Xcode:

| What | Where | Placeholder now |
| --- | --- | --- |
| Team | Signing & Capabilities of both `DatingCRM` and `DatingCRMShare` | none |
| Bundle identifier of the extension | `DatingCRMShare` > `PRODUCT_BUNDLE_IDENTIFIER`. It must be the app's identifier plus a suffix. | `com.datingcrm.app.share` |
| App Group | Build setting `APP_GROUP` on both targets, same value. Register the group for your team (Xcode does it when you add it under App Groups). | `group.com.datingcrm.app` |
| Keychain access group | Build setting `KEYCHAIN_GROUP` on both targets, same value. Your team ID is put in front of it. | `com.datingcrm.app` |

- `Info.plist` and the entitlements files read both settings, so nothing else needs editing.
- The token is stored in the first Keychain access group of the entitlements. Keep the shared group first in both files.
- After updating from a build without the extension, sign out and in again once: the old session is in the app's own defaults and Keychain group, which the extension cannot read.
- The tests cover `ScreenshotImport` and the upload request. Not verified, because the extension needs a signed build: that Dating CRM shows up in the share sheet, that the picture arrives from the share sheet, that the extension reads the app's URL and token through the two groups, and the screen itself. In the simulator the project builds and embeds the extension; nothing more was tried.

## Push notifications

After sign-in the app asks for permission to notify, gets a device token from Apple and sends it to the server with `POST /devices`. It does this on every launch. Tapping a push that carries a `card_id` switches to the Pipeline tab and opens that card.

- Push needs a real iPhone, a paid Apple developer account and the server's `APNS_*` settings (see `docs/modules/push-notifications.md`). Run from Xcode, the app gets a sandbox token, so the server also needs `APNS_SANDBOX=1`.
- The simulator gets no device token without an Apple account, so the tests cover only `Push`: the registration request and which card a tap opens. Not verified on a device: the permission prompt, the token arriving in `AppDelegate`, delivery of a push, and the tap opening the card on screen.
- Signing out unregisters the device: the server deletes it with this device's API token.

## Review queue

The Review tab shows `QueueView`: the review queue from `GET /queue`, hot leads first, each item led by the match's photo (or monogram) with its text on a glass plate. The match's name opens the card. A draft shows whether it is an opener or a reply, the dating app and the message it answers; it can be edited in place, then approved or dismissed (approve saves the edit first; dismiss offers Undo for 5 seconds before the server hears of it). A handover item says which trigger fired, quotes the message, and offers Copy on each suggested reply, "Hand back" and "Take over". A proposed paid item (Super Like, Rose, Boost) shows the candidate's photo, the item, its cost when the dating app reported one, the reason, a link to the profile, and "Approve" and "Decline"; the server spends it only on approve, and the item says so when the dating app did not spend it. Items of a kind the app does not know are skipped. See `docs/modules/ios-app-shell.md`, "Review".

A card that is paused for handover shows a banner at the end of its chat in `CardDetailView` (`Components/HandoverBanner.swift`): the trigger, the quoted message, the suggested replies, "Hand back" and "Take over" while the handover is pending, "Hand back" once the user took over. See `docs/modules/ios-app-shell.md`, "Card detail".

## Settings

Under You, the Autopilot screen holds Pause, autonomy, the AI budget and swipe limits (`AutopilotView`). The Settings section holds one screen each for the rest. Every switch calls the server at once and shows the state the server answers with; a failed call shows its error and leaves the switch as it was.

| Screen | Does | Routes |
| --- | --- | --- |
| Notifications (`NotificationsView`) | "Show names in pushes": push name previews, off by default. Off, a hot-lead or handover push says only "Someone replied. A draft is ready." Tapping any push opens its card. | `GET` and `PATCH /settings` (`push_name_previews`) |
| Privacy (`PrivacyView`) | Blur photos, the protected-trait opt-in and the AI disclosure. | `GET` and `PATCH /settings` (`blur_photos`), `GET` and `PUT /settings/protected-trait-guesses`, `/settings/ai-disclosure` |
| Activity log (`ActivityLogView`) | What the app did toward dating apps and the calendar, newest first: the action in words with the person's name (`ActivityEntry.summary`), the app, the time and what triggered it. | `GET /audit-log` |
| Find and purge (`PurgeView`) | Search by name or handle, tick the cards and swiped profiles of the person, type `purge`, then delete. The button names who it deletes ("Delete everything about Ada") and works only once someone is ticked and the word is typed (`PurgeConfirmation`). | `GET /people`, `GET /people/candidates`, `POST /people/purge` |

Not built: connector alerts have no screen.

## Swipe copilot

The Swipe tab shows `SwipeView`: the profiles from `GET /swipes`, each with the server's suggestion and its reason. "Find profiles" asks the server for new ones from Tinder. The user taps Like or Pass on every profile; the suggested one is bold. When the server could not reach the dating app, the swipe is saved and a line asks the user to swipe there by hand. Photos load straight from the dating app's image server.

## Call the API

All requests go through `APIClient`. To use a new route, add one method to it:

```swift
func drafts() async throws -> [Draft] {
    try await send("GET", "drafts")
}
```

JSON keys are converted between `snake_case` and `camelCase`. A `Date` field decodes from a plain day (`2026-12-01`, local midnight) or a full timestamp (`2026-11-20T10:00:00.123456Z`); dates are encoded as plain days.

A non-2xx answer throws `APIError(status:)`.

In a test, queue the server's answers on a `StubServer` and use its client:

```swift
let server = StubServer()
server.respond(#"[{"id": 1, "body": "Hi"}]"#)
let drafts = try await server.client().drafts()
#expect(server.requests.first?.url?.path() == "/drafts")
```

## Add a screen

1. Add `DatingCRM/Screens/<Name>View.swift`. Give the view a `let client: APIClient` and load data in `.task`. Build it from `DatingCRM/Components/`.
2. Put it in a tab in `MainTabView`, or link to it from a screen, for example with a `NavigationLink` in `YouView`.
3. Add the routes it needs to `APIClient`, each with a test in `DatingCRMTests/`.

Code is on the main actor by default (`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`), so views and `Session` need no `@MainActor` annotations.
