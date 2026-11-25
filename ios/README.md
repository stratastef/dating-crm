# Dating CRM for iOS

The SwiftUI client for the API in the repo root. It needs Xcode 27 and an iOS 18 or later simulator or device.

## Layout

| Path | Purpose |
| --- | --- |
| `DatingCRM.xcodeproj` | One app target and one unit test target. |
| `DatingCRM/DatingCRMApp.swift` | App entry: shows `SignInView` or `BoardView`, depending on `Session`. |
| `DatingCRM/Session.swift` | Sign-in state. Keeps the server URL in `UserDefaults` and the API token in the Keychain. |
| `DatingCRM/API/APIClient.swift` | Every call to the server. |
| `DatingCRM/API/Models.swift` | `Stage`, `Card`, `Message`: the JSON the server sends. |
| `DatingCRM/Screens/` | One file per screen. |
| `DatingCRMTests/` | Unit tests (Swift Testing). `StubServer` stands in for the server. |
| `Info.plist` | Only the keys that build settings cannot express. The rest of the Info.plist is generated. |

Both targets use folders that Xcode keeps in sync with the disk. A file you add under `DatingCRM/` or `DatingCRMTests/` is part of that target with no change to `project.pbxproj`, so branches that add files do not conflict on the project file. Do not put a file meant for one target in the other folder.

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
