# Dating CRM for iOS

The SwiftUI client for the API in the repo root. It needs Xcode 27 and an iOS 18 or later simulator or device.

## Layout

| Path | Purpose |
| --- | --- |
| `DatingCRM.xcodeproj` | The app target, the share extension target `DatingCRMShare` and one unit test target. |
| `DatingCRM/DatingCRMApp.swift` | App entry: shows `SignInView` or `BoardView`, depending on `Session`. |
| `DatingCRM/Session.swift` | Sign-in state. Keeps the server URL in `UserDefaults` and the API token in the Keychain. |
| `DatingCRM/ForegroundTimer.swift` | Measures each foreground stretch; the app entry reports it with `POST /time` when the app leaves the foreground. |
| `DatingCRM/Push.swift` | `Push` (device token, tapped card) and `AppDelegate`, which receives both from UIKit. |
| `DatingCRM.entitlements` | The push notification entitlement. |
| `DatingCRM/API/APIClient.swift` | Every call to the server. |
| `DatingCRM/API/Models.swift` | `Stage`, `Card`, `Message`, `Preferences`, `DashboardWeek`: the JSON the server sends. |
| `DatingCRM/Screens/` | One file per screen. |
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

`xcrun simctl list devices available` lists the simulator names you can use. The tests need no server.

To run on your own iPhone, open the project in Xcode, pick your team under Signing & Capabilities and change the bundle identifier `com.datingcrm.app` to one you own.

## Sign in

Start the server (see the root `README.md`) and create a user with `uv run python -m app.auth you@example.com`. In the app, paste the server URL and the token that command printed. The app checks them with one `GET /cards` before it keeps them.

A server on `localhost` or your local network may use plain `http`. Any other server needs `https`.

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

After sign-in the app asks for permission to notify, gets a device token from Apple and sends it to the server with `POST /devices`. It does this on every launch. Tapping a push that carries a `card_id` opens that card on top of the board.

- Push needs a real iPhone, a paid Apple developer account and the server's `APNS_*` settings (see the root `README.md`). Run from Xcode, the app gets a sandbox token, so the server also needs `APNS_SANDBOX=1`.
- The simulator gets no device token without an Apple account, so the tests cover only `Push`: the registration request and which card a tap opens. Not verified on a device: the permission prompt, the token arriving in `AppDelegate`, delivery of a push, and the tap opening the card on screen.
- Signing out does not unregister the device. The phone keeps getting that user's pushes until someone else signs in on it.

## Call the API

All requests go through `APIClient`. To use a new route, add one method to it:

```swift
func drafts() async throws -> [Draft] {
    try await send("GET", "drafts")
}
```

JSON keys are converted between `snake_case` and `camelCase`. The coders read and write dates as plain days (`2026-12-01`), which is all the app uses so far. Change the date strategy in `APIClient` when a screen needs a timestamp.

A non-2xx answer throws `APIError(status:)`.

In a test, queue the server's answers on a `StubServer` and use its client:

```swift
let server = StubServer()
server.respond(#"[{"id": 1, "body": "Hi"}]"#)
let drafts = try await server.client().drafts()
#expect(server.requests.first?.url?.path() == "/drafts")
```

## Add a screen

1. Add `DatingCRM/Screens/<Name>View.swift`. Give the view a `let client: APIClient` and load data in `.task`.
2. Link to it from an existing screen, for example with a `NavigationLink` in `BoardView`.
3. Add the routes it needs to `APIClient`, each with a test in `DatingCRMTests/`.

Code is on the main actor by default (`SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`), so views and `Session` need no `@MainActor` annotations.
