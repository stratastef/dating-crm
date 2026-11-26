import SwiftUI

/// Everything that limits what the app does alone: Pause, autonomy per job, the AI budget, the
/// privacy switches, and find-and-purge for a match who asks for their data to be deleted.
struct SettingsView: View {
    let client: APIClient
    /// The dating apps the user has cards on. Each gets its own pause switch.
    let apps: [String]

    @State private var pauses = Pauses()
    @State private var autonomy: [String: AutonomyLevel] = [:]
    @State private var budget: Budget?
    @State private var cap = ""
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
            killSwitch
            autonomySection
            budgetSection
            privacy
            purge
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await run {
                pauses = try await client.pauses()
                autonomy = try await client.autonomy()
                show(try await client.budget())
                protectedTraits = try await client.protectedTraitGuesses()
                disclosure = try await client.aiDisclosure()
            }
        }
    }

    private var killSwitch: some View {
        Section {
            Toggle("Pause all autopilot", isOn: paused(app: nil))
                .tint(.red)
            // An app paused on the server is listed even when the user has no card on it.
            ForEach(Set(apps).union(pauses.apps).sorted(), id: \.self) { app in
                Toggle("Pause \(app.capitalized)", isOn: paused(app: app))
            }
        } header: {
            Text("Pause")
        } footer: {
            Text("A pause stops what the app does alone. A draft you send yourself still goes out.")
        }
    }

    private var autonomySection: some View {
        Section {
            ForEach(autonomy.keys.sorted(), id: \.self) { job in
                Picker(job.capitalized, selection: level(job: job)) {
                    ForEach(AutonomyLevel.allCases) { Text($0.title).tag($0) }
                }
            }
        } header: {
            Text("Autonomy")
        } footer: {
            Text("Copilot: you approve everything. Autopilot and Full autopilot: the app acts alone within its limits.")
        }
    }

    private var budgetSection: some View {
        Section("AI budget") {
            if let budget {
                LabeledContent("Spent this month", value: budget.spendUsd.formatted(.currency(code: "USD")))
                if budget.paused {
                    Text("The cap is reached. Autopilot is paused until next month or a higher cap.")
                        .foregroundStyle(.red)
                }
            }
            HStack {
                TextField("Monthly cap in USD", text: $cap)
                    .keyboardType(.decimalPad)
                Button("Set cap") {
                    Task { await run { show(try await client.setBudgetCap(Double(cap) ?? 0)) } }
                }
                .disabled(Double(cap) == nil)
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
                Text(purgeResult).foregroundStyle(.secondary)
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

    private func paused(app: String?) -> Binding<Bool> {
        Binding {
            app.map(pauses.apps.contains) ?? pauses.all
        } set: { on in
            Task { await run { pauses = try await client.setPaused(on, app: app) } }
        }
    }

    private func level(job: String) -> Binding<AutonomyLevel> {
        Binding {
            autonomy[job] ?? .off
        } set: { level in
            Task { await run { autonomy = try await client.setAutonomy(job: job, level: level) } }
        }
    }

    private func show(_ budget: Budget) {
        self.budget = budget
        cap = budget.capUsd.formatted(.number.grouping(.never))
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
