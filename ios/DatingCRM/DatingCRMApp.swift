import SwiftUI

@main
struct DatingCRMApp: App {
    @UIApplicationDelegateAdaptor private var appDelegate: AppDelegate
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            if let client = session.client {
                let push = appDelegate.push
                BoardView(client: client, push: push, signOut: session.signOut)
                    .task { await push.requestPermission() }
                    // Runs again when Apple delivers the device token.
                    .task(id: push.deviceToken) { await push.register(with: client) }
            } else {
                SignInView(session: session)
            }
        }
    }
}
