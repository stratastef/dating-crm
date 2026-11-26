import SwiftUI

/// Privacy: Blur photos, protected-trait guesses and the AI disclosure. Every switch calls the server at once and
/// shows the state it answers with; a failed call shows its error and leaves the switch as it was.
struct PrivacyView: View {
    let client: APIClient

    @AppStorage(BlurredFace.key) private var blurPhotos = false
    @State private var protectedTraits = false
    @State private var disclosure = true
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
            }
            Section {
                Toggle("Blur photos", isOn: Binding { blurPhotos } set: { on in
                    Task { await run { blurPhotos = try await client.setBlurPhotos(on).blurPhotos } }
                })
            } footer: {
                explanation("Faces stay blurred in lists, Review and Swipe until you tap one. For using the app in public.")
            }
            Section {
                Toggle("Guess protected traits", isOn: Binding { protectedTraits } set: { on in
                    Task { await run { try await client.setProtectedTraitGuesses(on); protectedTraits = on } }
                })
            } footer: {
                explanation("""
                Protected traits are ethnicity, religion, health, sexuality and politics. The match read leaves them \
                out unless you turn this on.
                """)
            }
            Section {
                Toggle("Disclose the AI", isOn: Binding { disclosure } set: { on in
                    Task { await run { try await client.setAIDisclosure(on); disclosure = on } }
                })
            } footer: {
                explanation("""
                With this on, the first message autopilot sends to a match says that an AI helps you write. Keep it \
                on where the law requires it, such as the EU.
                """)
            }
        }
        // Under the root `.tint(.primary)` an "on" switch is white on white in dark mode.
        .tint(.green)
        .navigationTitle("Privacy")
        .task {
            await run {
                blurPhotos = try await client.settings().blurPhotos
                protectedTraits = try await client.protectedTraitGuesses()
                disclosure = try await client.aiDisclosure()
            }
        }
    }

    private func explanation(_ text: String) -> some View {
        Text(text).fontDesign(.serif).foregroundStyle(.secondaryText)
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
