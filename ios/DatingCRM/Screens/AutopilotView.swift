import SwiftUI

/// What the app may do alone: Pause first, then the night window, the autonomy level per job, the AI budget and the
/// swipe limits.
struct AutopilotView: View {
    let client: APIClient

    /// The dating apps the user has cards on. Each gets its own pause switch.
    @State private var apps: [String] = []
    @State private var pauses = Pauses()
    @State private var autonomy: [String: AutonomyLevel] = [:]
    @State private var budget: Budget?
    @State private var cap = ""
    @State private var perRun = ""
    @State private var perDay = ""
    /// Holds the night window; nil until loaded.
    @State private var settings: UserSettings?
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Label(error, systemImage: "exclamationmark.triangle")
            }
            pauseSection
            nightSection
            AutonomySections(levels: autonomy) { job, level in
                Task { await run { autonomy = try await client.setAutonomy(job: job, level: level) } }
            }
            budgetSection
            limitsSection
        }
        .scrollDismissesKeyboard(.interactively)
        .navigationTitle("Autopilot")
        .task {
            await run {
                pauses = try await client.pauses()
                autonomy = try await client.autonomy()
                show(try await client.budget())
                show(try await client.swipeLimits())
                settings = try await client.settings()
                apps = Set(try await client.cards().map(\.app)).sorted()
            }
        }
    }

    private var pauseSection: some View {
        Section {
            Toggle("Pause all apps", isOn: paused(app: nil))
            // An app paused on the server is listed even when the user has no card on it.
            ForEach(Set(apps).union(pauses.apps).sorted(), id: \.self) { app in
                Toggle("Pause \(app.capitalized)", isOn: paused(app: app))
            }
        } header: {
            header("Pause")
        } footer: {
            explanation("A pause stops what the app does alone. What you tap yourself still happens.")
        }
        // Under the root `.tint(.primary)` an "on" switch is white on white in dark mode. Pause must read at a glance.
        .tint(.green)
    }

    private var nightSection: some View {
        Section {
            if let settings {
                Picker("From", selection: nightHour(\.nightWindowStart, settings)) { hours }
                Picker("Until", selection: nightHour(\.nightWindowEnd, settings)) { hours }
            }
        } header: {
            header("Night window")
        } footer: {
            explanation("Autopilot sends nothing between these times, in your time zone. A reply due then goes out just after.")
        }
    }

    private var hours: some View {
        ForEach(0..<24, id: \.self) { hour in
            let time = Calendar.current.date(bySettingHour: hour, minute: 0, second: 0, of: .now)!
            Text(time.formatted(date: .omitted, time: .shortened)).tag(hour)
        }
    }

    /// One end of the night window. A change saves both ends, as the server now holds them.
    private func nightHour(_ end: WritableKeyPath<UserSettings, Int>, _ current: UserSettings) -> Binding<Int> {
        Binding {
            current[keyPath: end]
        } set: { hour in
            var changed = current
            changed[keyPath: end] = hour
            Task {
                await run { settings = try await client.setNightWindow(start: changed.nightWindowStart, end: changed.nightWindowEnd) }
            }
        }
    }

    private var budgetSection: some View {
        Section {
            if let budget {
                LabeledContent("Spent this month") {
                    Text(budget.spentOfCap).foregroundStyle(Color.primary)  // the system grey is under 4.5:1
                }
                if budget.paused {
                    Label("The budget is reached. Autopilot is paused until next month or a higher cap.",
                          systemImage: "exclamationmark.triangle")
                }
            }
            LabeledContent("Monthly cap in USD") {
                TextField("30", text: $cap)
                    .keyboardType(.decimalPad)
                    .multilineTextAlignment(.trailing)
            }
            Button("Save cap") {
                Task { await run { show(try await client.setBudgetCap(Double(cap) ?? 0)) } }
            }
            .buttonStyle(.secondaryCapsule)
            .listRowSeparator(.hidden)
            .disabled(Double(cap) == nil)
        } header: {
            header("AI budget")
        }
    }

    private var limitsSection: some View {
        Section {
            LabeledContent("Swipes per run") {
                TextField("1 to 10", text: $perRun)
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.trailing)
            }
            LabeledContent("Swipes per day") {
                TextField("1 to 100", text: $perDay)
                    .keyboardType(.numberPad)
                    .multilineTextAlignment(.trailing)
            }
            Button("Save limits") {
                guard let limits else { return }
                Task { await run { show(try await client.setSwipeLimits(limits)) } }
            }
            .buttonStyle(.secondaryCapsule)
            .listRowSeparator(.hidden)
            .disabled(limits == nil)
        } header: {
            header("Swipe limits")
        } footer: {
            explanation("""
            How many profiles autopilot may swipe on for each app: per hourly run, 1 to 10, and per day, 1 to 100. \
            Keep them low: fast swiping can get an account banned.
            """)
        }
    }

    /// The typed limits, or nil while either is outside what the server allows.
    private var limits: SwipeLimits? {
        guard let perRun = Int(perRun), let perDay = Int(perDay), (1...10).contains(perRun), (1...100).contains(perDay)
        else { return nil }
        return SwipeLimits(swipesPerRun: perRun, swipesPerDay: perDay)
    }

    private func header(_ title: String) -> some View {
        Text(title).foregroundStyle(Color.primary)
    }

    private func explanation(_ text: String) -> some View {
        Text(text).fontDesign(.serif).foregroundStyle(.secondaryText)
    }

    private func paused(app: String?) -> Binding<Bool> {
        Binding {
            app.map(pauses.apps.contains) ?? pauses.all
        } set: { on in
            Task { await run { pauses = try await client.setPaused(on, app: app) } }
        }
    }

    private func show(_ budget: Budget) {
        self.budget = budget
        cap = budget.capUsd.formatted(.number.grouping(.never))
    }

    private func show(_ limits: SwipeLimits) {
        perRun = String(limits.swipesPerRun)
        perDay = String(limits.swipesPerDay)
    }

    /// Runs one server call and shows its error on top of the list. A switch that failed keeps its old state.
    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
