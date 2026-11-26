import SwiftUI

/// The user's own things: dashboard, preferences, photos, settings, and Sign out.
struct YouView: View {
    let client: APIClient
    let signOut: () -> Void

    var body: some View {
        List {
            NavigationLink("Dashboard") { DashboardView(client: client) }
            NavigationLink("Preferences") { PreferencesView(client: client) }
            NavigationLink("Photos") { PhotosView(client: client) }
            NavigationLink("Settings") { SettingsView(client: client) }
            Button("Sign out", action: signOut)
        }
        .navigationTitle("You")
    }
}
