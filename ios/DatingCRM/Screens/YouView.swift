import SwiftUI

/// The user's own things, opening with the Dashboard headline: autopilot controls, preferences, connected apps, calendar,
/// profile (photos, bios and prompts, voice), notifications, privacy, the activity log, find and purge, and Sign out.
struct YouView: View {
    let client: APIClient
    let signOut: () async throws -> Void

    @State private var confirmsSignOut = false
    @State private var signOutError: String?
    // Until it loads, or if it fails, the row reads "Dashboard"; the Dashboard screen shows the error.
    @State private var dashboard: Dashboard?

    // `DCRM_OPEN=voice` pushes that screen on launch, for scripted simulator checks (see `Session.init`).
    @State private var opened = ProcessInfo.processInfo.environment["DCRM_OPEN"]

    var body: some View {
        List {
            NavigationLink {
                DashboardView(client: client)
            } label: {
                if let dashboard { DashboardHeadline(dashboard: dashboard) } else { Text("Dashboard") }
            }
            NavigationLink("Autopilot") { AutopilotView(client: client) }
            NavigationLink("Preferences") { PreferencesView(client: client) }
            NavigationLink("Swipe layout") { swipeLayout }
            NavigationLink("Connected apps") { ConnectedAppsView(client: client) }
            NavigationLink("Calendar") { CalendarView(client: client) }
            Section {
                NavigationLink("Photos") { PhotosView(client: client) }
                NavigationLink("Bios and prompts") { BiosView(client: client) }
                NavigationLink("Voice") { VoiceView(client: client) }
            } header: {
                Text("Profile").foregroundStyle(Color.primary)
            }
            Section {
                NavigationLink("Notifications") { NotificationsView(client: client) }
                NavigationLink("Privacy") { PrivacyView(client: client) }
                NavigationLink("Activity log") { ActivityLogView(client: client) }
                NavigationLink("Find and purge") { PurgeView(client: client) }
            } header: {
                Text("Settings").foregroundStyle(Color.primary)
            }
            Section {
                Button("Sign out") { confirmsSignOut = true }
                    .confirmationDialog("Sign out of Dating CRM?", isPresented: $confirmsSignOut, titleVisibility: .visible) {
                        Button("Sign out", role: .destructive) { Task { await attemptSignOut() } }
                    } message: {
                        Text("This phone stops getting your notifications. Your other devices stay signed in.")
                    }
                if let signOutError {
                    ErrorRow(text: signOutError) { await attemptSignOut() }
                }
            } header: {
                Text("Account").foregroundStyle(Color.primary)
            }
        }
        .navigationTitle("You")
        .task { dashboard = try? await client.dashboard() }
        .navigationDestination(item: $opened) { screen in
            switch screen {
            case "dashboard": DashboardView(client: client)
            case "autopilot": AutopilotView(client: client)
            case "voice": VoiceView(client: client)
            case "preferences": PreferencesView(client: client)
            case "connected-apps": ConnectedAppsView(client: client)
            case "calendar": CalendarView(client: client)
            case "swipe-layout": swipeLayout
            case "photos": PhotosView(client: client)
            case "bios": BiosView(client: client)
            case "notifications": NotificationsView(client: client)
            case "privacy": PrivacyView(client: client)
            case "activity-log": ActivityLogView(client: client)
            case "purge": PurgeView(client: client)
            default: EmptyView()
            }
        }
    }

    private func attemptSignOut() async {
        do {
            try await signOut()
        } catch {
            signOutError = "You're still signed in: the server could not be reached, so this phone still gets your notifications. Tap to try again."
        }
    }

    private var swipeLayout: some View {
        List { SwipeLayoutSection(client: client) }.navigationTitle("Swipe layout")
    }
}
