import SwiftUI

/// What a push shows on a locked phone. Tapping any push opens its card (`MainTabView`).
struct NotificationsView: View {
    let client: APIClient

    @State private var namePreviews = false
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
            }
            Section {
                Toggle("Show names in pushes", isOn: Binding { namePreviews } set: { on in
                    Task { await run { namePreviews = try await client.setPushNamePreviews(on).pushNamePreviews } }
                })
            } footer: {
                Text("""
                Off, a push about a match says only "Someone replied. A draft is ready." On, it names them and can \
                quote suggested replies, on the lock screen too. Tapping a push opens the card.
                """)
                .fontDesign(.serif)
                .foregroundStyle(.secondaryText)
            }
        }
        // Under the root `.tint(.primary)` an "on" switch is white on white in dark mode.
        .tint(.green)
        .navigationTitle("Notifications")
        .task { await run { namePreviews = try await client.settings().pushNamePreviews } }
    }

    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
