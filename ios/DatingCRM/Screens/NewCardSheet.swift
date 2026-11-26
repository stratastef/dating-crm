import SwiftUI

/// Adds a card by hand, for a match on an app without a connector.
struct NewCardSheet: View {
    let client: APIClient
    let onAdded: (Card) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var app = ""
    @State private var stage = Stage.matched
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                if let error {
                    Text(error).foregroundStyle(.red)
                }
                TextField("Name", text: $name)
                    .textContentType(.name)
                TextField("Dating app", text: $app)
                    .textInputAutocapitalization(.never)
                Picker("Stage", selection: $stage) {
                    ForEach(Stage.allCases) { Text($0.title).tag($0) }
                }
            }
            .navigationTitle("Add card")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Add") { Task { await add() } }
                        .disabled(trimmed(name).isEmpty || trimmed(app).isEmpty)
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func add() async {
        do {
            // The server keys connectors by the lowercase app name, as in `tinder`.
            onAdded(try await client.addCard(name: trimmed(name), app: trimmed(app).lowercased(), stage: stage))
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func trimmed(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespaces)
    }
}
