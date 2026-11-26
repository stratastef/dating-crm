import SwiftUI

/// The user's own things: dashboard, autopilot controls, preferences, profile (photos, voice), settings, and Sign out.
struct YouView: View {
    let client: APIClient
    let signOut: () -> Void

    // `DCRM_OPEN=voice` pushes that screen on launch, for scripted simulator checks (see `Session.init`).
    @State private var opened = ProcessInfo.processInfo.environment["DCRM_OPEN"]

    var body: some View {
        List {
            NavigationLink("Dashboard") { DashboardView(client: client) }
            NavigationLink("Autopilot") { AutopilotView(client: client) }
            NavigationLink("Preferences") { PreferencesView(client: client) }
            Section {
                NavigationLink("Photos") { PhotosView(client: client) }
                NavigationLink("Voice") { VoiceView(client: client) }
            } header: {
                Text("Profile").foregroundStyle(Color.primary)
            }
            Section {
                NavigationLink("Settings") { SettingsView(client: client) }
                Button("Sign out", action: signOut)
            } header: {
                Text("Account").foregroundStyle(Color.primary)
            }
        }
        .navigationTitle("You")
        .navigationDestination(item: $opened) { screen in
            switch screen {
            case "voice": VoiceView(client: client)
            case "preferences": PreferencesView(client: client)
            default: EmptyView()
            }
        }
    }
}
