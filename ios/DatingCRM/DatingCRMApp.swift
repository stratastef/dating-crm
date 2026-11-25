import SwiftUI

@main
struct DatingCRMApp: App {
    @State private var session = Session()
    @State private var timer = ForegroundTimer()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if let client = session.client {
                    BoardView(client: client, signOut: session.signOut)
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
