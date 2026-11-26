import SwiftUI

/// Find and purge, for a match who asks for their data to be deleted. The button names who it deletes.
struct PurgeView: View {
    let client: APIClient

    @State private var query = ""
    @State private var foundCards: [Card] = []
    @State private var foundCandidates: [SwipeCandidate] = []
    @State private var chosenCards: Set<Int> = []
    @State private var chosenCandidates: Set<Int> = []
    @State private var confirmation = ""
    @State private var purgeResult: String?
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
            }
            Section {
                HStack {
                    TextField("Name or handle", text: $query)
                        .autocorrectionDisabled()
                        .onSubmit { Task { await find() } }
                    Button("Find") { Task { await find() } }
                        .buttonStyle(.borderless)
                        .frame(minWidth: 44, minHeight: 44)
                        .disabled(query.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .alignmentGuide(.listRowSeparatorLeading) { _ in 0 }  // else it starts under Find
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
                if let purgeResult {
                    Text(purgeResult).foregroundStyle(.secondaryText)
                }
            } footer: {
                Text("""
                For a match who asks for their data to be deleted: their card and everything stored about them, \
                and the app will not store them again.
                """)
                    .fontDesign(.serif)
                    .foregroundStyle(.secondaryText)
            }
            if !chosenNames.isEmpty {
                Section {
                    TextField("Type \(PurgeConfirmation.word) to confirm", text: $confirmation)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button(PurgeConfirmation.button(names: chosenNames), role: .destructive) {
                        Task { await purgeChosen() }
                    }
                    .buttonStyle(.primaryCapsule)
                    .listRowSeparator(.hidden)
                    .disabled(!PurgeConfirmation.allows(typed: confirmation, chosen: chosenNames.count))
                } footer: {
                    Text("It cannot be undone.").fontDesign(.serif).foregroundStyle(.secondaryText)
                }
            }
        }
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle("Find and purge")
    }

    /// Who the button deletes, in the order they are listed.
    private var chosenNames: [String] {
        foundCards.filter { chosenCards.contains($0.id) }.map(\.name)
            + foundCandidates.filter { chosenCandidates.contains($0.id) }.map(\.name)
    }

    private func choice(_ title: String, chosen: Bool, toggle: @escaping () -> Void) -> some View {
        Button(action: toggle) {
            HStack {
                Text(title)
                Spacer()
                Image(systemName: chosen ? "checkmark.circle.fill" : "circle")
            }
            .frame(minHeight: 44)
            .contentShape(.rect)
        }
        .foregroundStyle(.primary)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }

    private func find() async {
        guard !query.trimmingCharacters(in: .whitespaces).isEmpty else { return }
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
        let names = chosenNames
        await run {
            _ = try await client.purge(cardIDs: chosenCards.sorted(), candidateIDs: chosenCandidates.sorted())
            foundCards.removeAll { chosenCards.contains($0.id) }
            foundCandidates.removeAll { chosenCandidates.contains($0.id) }
            chosenCards = []
            chosenCandidates = []
            confirmation = ""
            purgeResult = "Deleted everything about \(names.formatted(.list(type: .and)))."
        }
    }

    /// Runs one server call and shows its error on top of the list.
    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
