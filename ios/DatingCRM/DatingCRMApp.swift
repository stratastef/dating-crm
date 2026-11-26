import SwiftUI

@main
struct DatingCRMApp: App {
    @UIApplicationDelegateAdaptor private var appDelegate: AppDelegate
    @State private var session = Session()
    @State private var timer = ForegroundTimer()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if let client = session.client {
                    let push = appDelegate.push
                    MainTabView(client: client, push: push, signOut: session.signOut)
                        .task {
                            // A scripted simulator check (see `Session.init`) cannot answer the permission alert.
                            if ProcessInfo.processInfo.environment["DCRM_TOKEN"] == nil { await push.requestPermission() }
                        }
                        // Runs again when Apple delivers the device token.
                        .task(id: push.deviceToken) { await push.register(with: client) }
                } else {
                    SignInView(session: session)
                }
            }
            .onChange(of: scenePhase, initial: true) { _, phase in
                // shortcut: a stretch is lost if the app is killed in the foreground or iOS suspends it before
                // the request is sent; store unsent stretches on disk if the dashboard needs exact hours.
                if let seconds = timer.phaseChanged(active: phase == .active, now: .now), let client = session.client {
                    Task { try? await client.recordTime(seconds: seconds) }
                }
            }
        }
    }
}
