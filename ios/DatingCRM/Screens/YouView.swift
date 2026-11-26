import SwiftUI

/// The user's own things: dashboard, preferences, photos, settings, and Sign out.
struct YouView: View {
    let client: APIClient
    let signOut: () async -> Void

    @State private var confirmsSignOut = false

    var body: some View {
        List {
            NavigationLink("Dashboard") { DashboardView(client: client) }
            NavigationLink("Preferences") { PreferencesView(client: client) }
            NavigationLink("Photos") { PhotosView(client: client) }
            NavigationLink("Settings") { SettingsView(client: client) }
            Button("Sign out") { confirmsSignOut = true }
                .confirmationDialog("Sign out of Dating CRM?", isPresented: $confirmsSignOut, titleVisibility: .visible) {
                    Button("Sign out", role: .destructive) { Task { await signOut() } }
                } message: {
                    Text("This phone stops getting your notifications. Your other devices stay signed in.")
                }
        }
        .navigationTitle("You")
    }
}
