import SwiftUI

/// What the user wants: wishes in plain words, must-haves and dealbreakers.
struct PreferencesView: View {
    let client: APIClient

    @State private var saved = Preferences()
    @State private var preferences = Preferences()
    @State private var error: String?

    var body: some View {
        Form {
            if let error {
                Text(error).foregroundStyle(.red)
            }

            Section("Wishes") {
                TextField("What you want, in your own words", text: $preferences.wishes, axis: .vertical)
                    .lineLimit(3...)
            }

            items("Must-haves", "Must-have", $preferences.mustHaves)
            items("Dealbreakers", "Dealbreaker", $preferences.dealbreakers)
        }
        .navigationTitle("Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Button("Save") {
                Task { await save() }
            }
            .disabled(preferences == saved)
        }
        .task {
            do {
                saved = try await client.preferences()
                preferences = saved
            } catch {
                self.error = error.localizedDescription
            }
        }
    }

    private func items(_ title: String, _ placeholder: String, _ items: Binding<[String]>) -> some View {
        Section(title) {
            ForEach(items.wrappedValue.indices, id: \.self) { index in
                TextField(placeholder, text: items[index])
            }
            .onDelete { items.wrappedValue.remove(atOffsets: $0) }
            Button("Add \(placeholder.lowercased())") { items.wrappedValue.append("") }
        }
    }

    private func save() async {
        do {
            // Rows the user added and left blank are not preferences.
            preferences.mustHaves.removeAll { $0.trimmingCharacters(in: .whitespaces).isEmpty }
            preferences.dealbreakers.removeAll { $0.trimmingCharacters(in: .whitespaces).isEmpty }
            saved = try await client.save(preferences)
            preferences = saved
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
