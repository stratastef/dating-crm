import SwiftUI

/// The user's own things: dashboard, autopilot controls, preferences, connected apps, calendar, profile (photos, voice),
/// settings, and Sign out.
struct YouView: View {
    let client: APIClient
    let signOut: () async -> Void

    @State private var confirmsSignOut = false

    // `DCRM_OPEN=voice` pushes that screen on launch, for scripted simulator checks (see `Session.init`).
    @State private var opened = ProcessInfo.processInfo.environment["DCRM_OPEN"]

    var body: some View {
        List {
            NavigationLink("Dashboard") { DashboardView(client: client) }
            NavigationLink("Autopilot") { AutopilotView(client: client) }
            NavigationLink("Preferences") { PreferencesView(client: client) }
            NavigationLink("Connected apps") { ConnectedAppsView(client: client) }
            NavigationLink("Calendar") { CalendarView(client: client) }
            Section {
                NavigationLink("Photos") { PhotosView(client: client) }
                NavigationLink("Voice") { VoiceView(client: client) }
            } header: {
                Text("Profile").foregroundStyle(Color.primary)
            }
            Section {
                NavigationLink("Settings") { SettingsView(client: client) }
                Button("Sign out") { confirmsSignOut = true }
                    .confirmationDialog("Sign out of Dating CRM?", isPresented: $confirmsSignOut, titleVisibility: .visible) {
                        Button("Sign out", role: .destructive) { Task { await signOut() } }
                    } message: {
                        Text("This phone stops getting your notifications. Your other devices stay signed in.")
                    }
            } header: {
                Text("Account").foregroundStyle(Color.primary)
            }
        }
        .navigationTitle("You")
        .navigationDestination(item: $opened) { screen in
            switch screen {
            case "voice": VoiceView(client: client)
            case "preferences": PreferencesView(client: client)
            case "connected-apps": ConnectedAppsView(client: client)
            case "calendar": CalendarView(client: client)
            default: EmptyView()
            }
        }
    }
}
