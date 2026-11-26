import SwiftUI

/// The privacy switches, and find-and-purge for a match who asks for their data to be deleted. Pause, autonomy,
/// the AI budget and swipe limits are on `AutopilotView`.
struct SettingsView: View {
    let client: APIClient

    @State private var protectedTraits = false
    @State private var disclosure = true
    @State private var error: String?

    @State private var query = ""
    @State private var foundCards: [Card] = []
    @State private var foundCandidates: [SwipeCandidate] = []
    @State private var chosenCards: Set<Int> = []
    @State private var chosenCandidates: Set<Int> = []
    @State private var confirmation = ""
    @State private var purgeResult: String?

    var body: some View {
        Form {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            privacy
            purge
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await run {
                protectedTraits = try await client.protectedTraitGuesses()
                disclosure = try await client.aiDisclosure()
            }
        }
    }

    private var privacy: some View {
        Section {
            Toggle("Guess protected traits", isOn: Binding { protectedTraits } set: { on in
                Task { await run { try await client.setProtectedTraitGuesses(on); protectedTraits = on } }
            })
            Toggle("Disclose the AI", isOn: Binding { disclosure } set: { on in
                Task { await run { try await client.setAIDisclosure(on); disclosure = on } }
            })
        } header: {
            Text("Privacy")
        } footer: {
            Text("""
            Protected traits are ethnicity, religion, health, sexuality and politics; the match read leaves \
            them out unless you opt in. With the disclosure on, the first message sent alone to a match says \
            that an AI helps you write. Keep it on where the law requires it, such as the EU.
            """)
        }
    }

    private var purge: some View {
        Section {
            HStack {
                TextField("Name or handle", text: $query)
                    .autocorrectionDisabled()
                Button("Find") { Task { await find() } }
                    .disabled(query.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            ForEach(foundCards) { card in
                choice("\(card.name), \(card.app.capitalized) match", chosen: chosenCards.contains(card.id)) {
                    chosenCards.formSymmetricDifference([card.id])
                }
            }
            ForEach(foundCandidates) { candidate in
                choice(
                    "\(candidate.name), \(candidate.app.capitalized) profile",
                    chosen: chosenCandidates.contains(candidate.id)
                ) {
                    chosenCandidates.formSymmetricDifference([candidate.id])
                }
            }
            if !foundCards.isEmpty || !foundCandidates.isEmpty {
                TextField("Type \(PurgeConfirmation.word) to confirm", text: $confirmation)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                Button("Delete \(chosen) and all their data", role: .destructive) {
                    Task { await purgeChosen() }
                }
                .disabled(!PurgeConfirmation.allows(typed: confirmation, chosen: chosen))
            }
            if let purgeResult {
                Text(purgeResult).foregroundStyle(.secondaryText)
            }
        } header: {
            Text("Find and purge")
        } footer: {
            Text("For a match who asks for their data to be deleted. It cannot be undone.")
        }
    }

    private var chosen: Int { chosenCards.count + chosenCandidates.count }

    private func choice(_ title: String, chosen: Bool, toggle: @escaping () -> Void) -> some View {
        Button(action: toggle) {
            HStack {
                Text(title)
                Spacer()
                Image(systemName: chosen ? "checkmark.circle.fill" : "circle")
            }
        }
        .foregroundStyle(.primary)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }

    private func find() async {
        await run {
            foundCards = try await client.findPeople(query)
            foundCandidates = try await client.findCandidates(query)
            chosenCards = []
            chosenCandidates = []
            confirmation = ""
            purgeResult = foundCards.isEmpty && foundCandidates.isEmpty ? "Nobody found." : nil
        }
    }

    private func purgeChosen() async {
        await run {
            let purged = try await client.purge(cardIDs: chosenCards.sorted(), candidateIDs: chosenCandidates.sorted())
            foundCards.removeAll { chosenCards.contains($0.id) }
            foundCandidates.removeAll { chosenCandidates.contains($0.id) }
            chosenCards = []
            chosenCandidates = []
            confirmation = ""
            purgeResult = "Deleted \(purged)."
        }
    }

    /// Runs one server call and shows its error on top of the form. A switch that failed keeps its old state.
    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
