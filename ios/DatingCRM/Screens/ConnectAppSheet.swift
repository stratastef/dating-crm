import SwiftUI

/// Connect or Reconnect: step-by-step instructions to get the app's session token, and a field to paste it.
/// The server stores the token, turns the connector on and syncs at once.
struct ConnectAppSheet: View {
    let client: APIClient
    let app: String
    let onConnected: () -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var token = ""
    @State private var error: String?
    @State private var connecting = false

    /// How to get each connector's session token. Tinder shows it only in a desktop browser's developer tools.
    // shortcut: a computer is needed until in-app Tinder sign-in exists (#62); replace these steps then.
    static let steps = [
        "tinder": [
            "You need a computer for this. On it, sign in at tinder.com in Chrome or Firefox.",
            "Open the developer tools (F12, or Option\u{2011}Command\u{2011}I on a Mac), choose the Network tab and reload the page.",
            "Click any request to api.gotinder.com and copy the value of its X-Auth-Token request header.",
            "Paste it below. A Mac signed in to your Apple Account shares its clipboard with this iPhone.",
        ],
    ]

    private var name: String { app.capitalized }
    private var trimmed: String { token.trimmingCharacters(in: .whitespacesAndNewlines) }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    ForEach(Array((Self.steps[app] ?? []).enumerated()), id: \.offset) { number, step in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text("\(number + 1).").monospacedDigit()
                            Text(step)
                        }
                        .fontDesign(.serif)
                    }
                } header: {
                    Text("Get your \(name) session token").foregroundStyle(Color.primary)
                }
                Section {
                    // The system placeholder grey is under 4.5:1.
                    SecureField("Session token", text: $token, prompt: Text("Session token").foregroundStyle(.secondaryText))
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .frame(minHeight: 44)
                    if let error {
                        Label(error, systemImage: "exclamationmark.triangle")
                    }
                    Button("Connect \(name)") { Task { await connect() } }
                        .buttonStyle(.primaryCapsule)
                        .listRowSeparator(.hidden)
                        .disabled(trimmed.isEmpty || connecting)
                } footer: {
                    Text("The token is a password for your \(name) account. Paste it only here.")
                        .fontDesign(.serif)
                        .foregroundStyle(.secondaryText)
                }
            }
            .scrollDismissesKeyboard(.immediately)
            .navigationTitle("Connect \(name)")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func connect() async {
        connecting = true
        defer { connecting = false }
        do {
            try await client.connect(app: app, token: trimmed)
            onConnected()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
