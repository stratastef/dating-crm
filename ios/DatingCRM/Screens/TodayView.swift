import SwiftUI

/// Today (ADR 0005): the review count over the color field, then Overdue, Today and Coming up.
struct TodayView: View {
    let client: APIClient
    /// Opens the Review tab: the count is the review queue's one row on Today.
    let openReview: () -> Void
    /// The Review tab's badge, set by each load.
    @Binding var reviewCount: Int

    @State private var today: Today?
    @State private var error: String?
    @State private var path: [Card] = []
    @State private var rating: Card?
    @State private var timeZoneSent = false
    @State private var scrolled: CGFloat = 0
    @State private var settingUp = false
    @State private var toast: Toast?
    @Environment(\.motionReduced) private var motionReduced
    @Environment(\.todayLoaded) private var todayLoaded

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Counter(review: today?.review ?? ReviewSummary(), action: openReview)
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                if let setup = today?.setup {
                    FinishSetupRow(stepsLeft: setup.stepsLeft) { settingUp = true } dismiss: {
                        Task { await dismissSetup() }
                    }
                }
                if let error {
                    ErrorRow(text: error) { await load() }
                }
                if let today {
                    if today.isEmpty {
                        ContentUnavailableView("Nothing for today", systemImage: "checkmark.circle")
                            .fontDesign(.serif)
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                    }
                    group("Overdue", today.overdue, accent: true)
                    group("Today", today.today)
                    group("Coming up", today.comingUp)
                }
            }
            .scrollContentBackground(.hidden)
            .background(alignment: .top) { field }
            // Only the first screenful matters to the field, so scrolling further changes nothing.
            .onScrollGeometryChange(for: CGFloat.self) { min(max($0.contentOffset.y + $0.contentInsets.top, 0), 500) } action: {
                scrolled = $1
            }
            .navigationTitle("Today")
            .navigationDestination(for: Card.self) { card in
                CardDetailView(client: client, card: card) { _ in }
            }
            .sheet(item: $rating) { card in
                DateRatingSheet(name: card.name) { stars, note in
                    Task { await rate(card, stars, note) }
                }
            }
            .fullScreenCover(isPresented: $settingUp, onDismiss: { Task { await load() } }) {
                SetupView(client: client) { settingUp = false }
            }
            .toast($toast)
            .refreshable { await load() }
            .task {
                await load()
                todayLoaded()
            }
        }
    }

    private func dismissSetup() async {
        do {
            try await client.setSetupDismissed(true)
            await load()
            toast = Toast(text: "Finish setup hidden. Every step stays under You.") {
                Task {
                    try? await client.setSetupDismissed(false)
                    await load()
                }
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// The soft color field under the status bar (ADR 0009): full with 3 or more waiting, softer with 1 or 2,
    /// gone at 0, and never with Reduce Motion or Low Power Mode. It scrolls away with the count.
    private var field: some View {
        let count = today?.review.count ?? 0
        return ZStack(alignment: .top) {
            Color(uiColor: .systemBackground)
            if !motionReduced {
                ColorField()
                    .frame(height: 360)
                    .opacity(count >= 3 ? 1 : count > 0 ? 0.55 : 0)
                    .offset(y: -scrolled)
                    .animation(.easeInOut(duration: 1.2), value: count)
            }
        }
        .ignoresSafeArea()
    }

    @ViewBuilder
    private func group(_ title: String, _ items: [TodayItem], accent: Bool = false) -> some View {
        if !items.isEmpty {
            Section {
                ForEach(items) { item in
                    if item.kind == .rateDate {
                        Button { rating = item.card } label: { TodayRow(item: item) }
                    } else {
                        NavigationLink(value: item.card) { TodayRow(item: item) }
                    }
                }
            } header: {
                HStack {
                    Text(title)
                    Spacer()
                    Text(items.count, format: .number)
                }
                .font(.headline)
                // The system's grey header is under 4.5:1; Overdue waits on the user, so it takes the accent.
                .foregroundStyle(accent ? Color.accent : Color.primary)
            }
        }
    }

    private func load() async {
        if !timeZoneSent {
            // Before the first load, so the server's "today" is the phone's. On failure the stored zone stays.
            timeZoneSent = (try? await client.setTimeZone(TimeZone.current.identifier)) != nil
        }
        do {
            let loaded = try await client.today()
            withAnimation(motionReduced ? .easeInOut : .smooth) { today = loaded }
            reviewCount = loaded.review.count
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func rate(_ card: Card, _ stars: Int, _ note: String) async {
        var card = card
        card.dateRating = stars
        card.dateNote = note
        do {
            _ = try await client.update(card)
            await load()
        } catch {
            self.error = "The rating was not saved. Check your connection, then rate the date again."
        }
    }
}

/// The review summary row: how many items wait in Review, large and rolling, and how many are hot leads.
private struct Counter: View {
    let review: ReviewSummary
    let action: () -> Void

    @Environment(\.motionReduced) private var motionReduced
    @ScaledMetric(relativeTo: .largeTitle) private var size: CGFloat = 76

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(review.count, format: .number)
                    .font(.system(size: size, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(.accent)
                    .contentTransition(motionReduced ? .opacity : .numericText(value: Double(review.count)))
                Text(title).font(.title3.weight(.semibold))
                Text(subtitle).foregroundStyle(.secondaryText)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens Review")
    }

    private var title: String {
        switch review.count {
        case 0: "Nothing waits on you"
        case 1: "reply waits for you"
        default: "replies wait for you"
        }
    }

    private var subtitle: String {
        switch review.hot {
        case 0: review.count == 0 ? "Autopilot has the rest." : "No hot leads."
        case 1: "1 is a hot lead."
        default: "\(review.hot) are hot leads."
        }
    }
}

/// "Finish setup" under the count: how many steps are left, opening setup on them, and a button to hide it.
private struct FinishSetupRow: View {
    let stepsLeft: Int
    let open: () -> Void
    let dismiss: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Button(action: open) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Finish setup").font(.headline)
                    Text(stepsLeft == 1 ? "1 step left" : "\(stepsLeft) steps left")
                        .font(.subheadline)
                        .foregroundStyle(.secondaryText)
                }
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(.rect)
            }
            Button(action: dismiss) {
                Image(systemName: "xmark").frame(width: 44, height: 44).contentShape(.rect)
            }
            .accessibilityLabel("Hide Finish setup")
        }
        // Two buttons in one row: plain, so each takes only its own taps.
        .buttonStyle(.plain)
    }
}

/// Indigo, amber and pink, fading into the page.
private struct ColorField: View {
    var body: some View {
        let page = Color(uiColor: .systemBackground)
        MeshGradient(
            width: 3, height: 3,
            points: [[0, 0], [0.5, 0], [1, 0], [0, 0.5], [0.4, 0.45], [1, 0.55], [0, 1], [0.5, 1], [1, 1]],
            colors: [
                .accent.opacity(0.55), .accent.opacity(0.35), Color(red: 0.96, green: 0.62, blue: 0.04).opacity(0.35),
                Color(red: 0.93, green: 0.28, blue: 0.6).opacity(0.2), .accent.opacity(0.12), Color(red: 0.96, green: 0.62, blue: 0.04).opacity(0.15),
                page, page, page,
            ]
        )
        .accessibilityHidden(true)
    }
}

/// A Today row: the face, the name or "Date with …", what to do, and when.
private struct TodayRow: View {
    let item: TodayItem

    var body: some View {
        HStack(spacing: 14) {
            Avatar(name: item.card.name, photo: item.card.leadPhotoUrl)
            AdaptiveStack {
                // Full width, so the time sits at the trailing edge, or under the text at accessibility sizes.
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.kind == .date ? "Date with \(item.card.name)" : item.card.name).font(.headline)
                    if let line {
                        Text(line).font(.subheadline).foregroundStyle(.secondaryText)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                time
                    .font(.subheadline)
                    // Overdue waits on the user.
                    .foregroundStyle(item.daysLate == nil ? Color.secondaryText : Color.accent)
            }
        }
    }

    private var line: String? {
        switch item.kind {
        case .date: nil
        case .nextAction: item.card.nextAction
        case .stalled: "Revive or archive"
        case .rateDate: "Rate your date"
        }
    }

    @ViewBuilder
    private var time: some View {
        switch item.kind {
        case .date:
            if let start = item.startsAt {
                let clock = start.formatted(date: .omitted, time: .shortened)
                Text(RelativeTime.daysFrom(.now, to: start) == 0 ? clock : "\(RelativeTime.day(start)) \(clock)")
            }
        case .nextAction:
            if let due = item.dueDate { Text(RelativeTime.due(due)) }
        case .stalled:
            if let last = item.card.lastActivity {
                Text("quiet \(RelativeTime.since(last))")
                    .accessibilityLabel("quiet, last message \(last.formatted(.relative(presentation: .named)))")
            }
        case .rateDate:
            if let changed = item.card.stageChangedAt { Text(RelativeTime.day(changed)) }
        }
    }
}
