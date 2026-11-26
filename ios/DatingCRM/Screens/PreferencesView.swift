import SwiftUI

/// What the user wants: wishes in plain words, must-haves and dealbreakers. They steer swipes and drafts. Edits save
/// as the user types; Edit deletes rows. Push it onto a navigation stack.
struct PreferencesView: View {
    let client: APIClient

    @State private var saved: Preferences?
    @State private var preferences = Preferences()
    @State private var error: String?

    /// The preferences to send: rows the user added and left blank are not preferences.
    private var wanted: Preferences {
        var wanted = preferences
        wanted.mustHaves.removeAll { $0.trimmingCharacters(in: .whitespaces).isEmpty }
        wanted.dealbreakers.removeAll { $0.trimmingCharacters(in: .whitespaces).isEmpty }
        return wanted
    }

    var body: some View {
        List {
            if let saved {
                Text("These steer swipes and drafts. A profile that shows a dealbreaker gets Pass automatically.")
                    .fontDesign(.serif)
                    .listRowSeparator(.hidden)
                Section {
                    GrowingField(label: "Wishes", prompt: "What you want, in your own words", text: $preferences.wishes)
                    failure(wanted.wishes != saved.wishes)
                } header: {
                    Text("Wishes").foregroundStyle(Color.primary)
                }
                items("Must-haves", "Must-have", \.mustHaves, unsaved: wanted.mustHaves != saved.mustHaves)
                items("Dealbreakers", "Dealbreaker", \.dealbreakers, unsaved: wanted.dealbreakers != saved.dealbreakers)
            } else if let error {
                ErrorRow(text: error) { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle("Preferences")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if saved != nil { EditButton() }
        }
        .scrollDismissesKeyboard(.immediately)
        .autosave(wanted, saved: saved ?? wanted) { await save($0) }
        // Once only: a reload on return could land before the save made on leaving, and undo it.
        .task { if saved == nil { await load() } }
    }

    private func items(
        _ title: String, _ placeholder: String, _ path: WritableKeyPath<Preferences, [String]>, unsaved: Bool
    ) -> some View {
        Section {
            ForEach(preferences[keyPath: path].indices, id: \.self) { index in
                // Bounds-checked: a deleted row's field can still read its index once after the removal.
                GrowingField(
                    label: placeholder, prompt: placeholder,
                    text: Binding(
                        get: { preferences[keyPath: path].indices.contains(index) ? preferences[keyPath: path][index] : "" },
                        set: { if preferences[keyPath: path].indices.contains(index) { preferences[keyPath: path][index] = $0 } }
                    ))
            }
            .onDelete { preferences[keyPath: path].remove(atOffsets: $0) }
            Button("Add \(placeholder.lowercased())") { preferences[keyPath: path].append("") }
                .frame(minHeight: 44)
            failure(unsaved)
        } header: {
            Text(title).foregroundStyle(Color.primary)
        }
    }

    @ViewBuilder private func failure(_ unsaved: Bool) -> some View {
        if let error, unsaved {
            ErrorRow(text: error) { await save(wanted) }
        }
    }

    private func load() async {
        do {
            let loaded = try await client.preferences()
            preferences = loaded
            saved = loaded
            error = nil
        } catch {
            self.error = "Your preferences did not load. Check your connection, then tap to try again."
        }
    }

    private func save(_ preferences: Preferences) async {
        do {
            saved = try await client.save(preferences)
            error = nil
        } catch {
            if !Task.isCancelled {
                self.error = "Not saved. Check your connection, then tap to try again."
            }
        }
    }
}
