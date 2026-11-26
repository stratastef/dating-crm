import SwiftUI

@main
struct DatingCRMApp: App {
    @UIApplicationDelegateAdaptor private var appDelegate: AppDelegate
    @State private var session = Session()
    @State private var timer = ForegroundTimer()
    // App state lives as long as the process: the splash shows on a cold launch, never on a resume.
    @State private var splash = true
    @State private var todayLoaded = false
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            // A ZStack, not a Group: a Group would give each screen its own copy of the modifiers below, so the
            // splash and the sign-in haptic would start over when sign-in hands over to the tabs.
            ZStack {
                if let client = session.client, session.isNewAccount {
                    SetupView(client: client) { session.isNewAccount = false }
                } else if let client = session.client {
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
            .environment(\.todayLoaded) { todayLoaded = true }
            .overlay {
                if splash {
                    // Only the tabs open on Today, whose data the splash waits for.
                    Splash(ready: todayLoaded || session.client == nil || session.isNewAccount) {
                        withAnimation(.easeInOut(duration: 0.3)) { splash = false }
                    }
                    .modifier(MotionReducedReader())
                    .transition(.opacity)
                }
            }
            // The sign-in code accepted (or a developer sign-in), as the server answered. Sign-in itself has gone.
            .sensoryFeedback(.done, trigger: session.client != nil) { was, now in !was && now }
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
