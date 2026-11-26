import SwiftUI

/// Setup (ADR 0001): the steps not done yet, in order, each one the screen that holds it under You. Every screen
/// saves as the user goes, so Next works whether the step was done or skipped. Right after a new account's first
/// sign-in all five steps are left; Today's "Finish setup" opens the rest.
struct SetupView: View {
    let client: APIClient
    let finish: () -> Void

    @State private var steps: [SetupStep.Step]?
    @State private var index = 0
    @State private var error: String?
    /// The last step's autonomy levels, nil until loaded.
    @State private var autonomy: [String: AutonomyLevel]?
    @State private var autonomyError: String?
    @State private var autonomyPicks = 0
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        NavigationStack {
            Group {
                if let steps, steps.indices.contains(index) {
                    page(steps[index])
                        .id(index)  // a new screen per step: the one left saves as it disappears
                        .safeAreaBar(edge: .bottom) { bar(steps.count) }
                } else if let error {
                    List { ErrorRow(text: error, retry: load) }
                } else {
                    ProgressView()
                }
            }
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Skip setup", action: finish) }
            }
        }
        // `MainTabView`'s root look, which setup is shown outside of.
        .tint(.primary)
        .listStyle(.plain)
        .modifier(MotionReducedReader())
        .task { await load() }
    }

    @ViewBuilder
    private func page(_ step: SetupStep.Step) -> some View {
        switch step {
        case .datingApps: ConnectedAppsView(client: client)
        case .calendar: CalendarView(client: client)
        case .voice: VoiceView(client: client)
        case .preferences: PreferencesView(client: client)
        case .swipeLayoutAndAutonomy:
            List {
                SwipeLayoutSection(client: client)
                if let autonomyError {
                    ErrorRow(text: autonomyError) { await loadAutonomy() }
                }
                if let autonomy {
                    AutonomySections(levels: autonomy) { job, level in
                        autonomyPicks += 1
                        Task { await saveAutonomy(job, level) }
                    }
                }
            }
            .sensoryFeedback(.tick, trigger: autonomyPicks)
            .navigationTitle("Swipe and autonomy")
            .task { await loadAutonomy() }
        }
    }

    /// Where the user is, that skipping is fine, and Next.
    private func bar(_ count: Int) -> some View {
        VStack(spacing: 10) {
            // At accessibility sizes the whole sentence would cover half the step.
            Text("Step \(index + 1) of \(count)" + (typeSize.isAccessibilitySize ? "" : ". Skip it if you like: it stays under You."))
                .font(.subheadline)
                .fontDesign(.serif)
                .foregroundStyle(.secondaryText)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button(index + 1 < count ? "Next" : "Done") { Task { await next() } }
                .buttonStyle(.primaryCapsule)
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
    }

    private func next() async {
        if steps?[index] == .swipeLayoutAndAutonomy, let autonomy {
            // Keeping the levels as shown is a choice too: store them, so the step counts as done.
            for (job, level) in autonomy { _ = try? await client.setAutonomy(job: job, level: level) }
        }
        if index + 1 < steps?.count ?? 0 { index += 1 } else { finish() }
    }

    private func load() async {
        do {
            let left = try await client.setup().filter { !$0.done }.map(\.step)
            if left.isEmpty {  // done meanwhile, on another device
                finish()
                return
            }
            #if DEBUG
            // `DCRM_SETUP=voice` opens setup on that step, for scripted simulator checks (see `Session.init`).
            let start = ProcessInfo.processInfo.environment["DCRM_SETUP"].flatMap(SetupStep.Step.init(rawValue:))
            index = start.flatMap(left.firstIndex(of:)) ?? 0
            #endif
            steps = left
            error = nil
        } catch {
            self.error = "Setup did not load. Check your connection, then tap to try again."
        }
    }

    private func loadAutonomy() async {
        do {
            autonomy = try await client.autonomy()
            autonomyError = nil
        } catch {
            autonomyError = "Your autonomy levels did not load. Tap to try again."
        }
    }

    /// A level that failed to save keeps its old choice on screen.
    private func saveAutonomy(_ job: String, _ level: AutonomyLevel) async {
        do {
            autonomy = try await client.setAutonomy(job: job, level: level)
            autonomyError = nil
        } catch {
            autonomyError = "Your autonomy level was not saved. Tap to reload, then choose again."
        }
    }
}
