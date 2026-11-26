import SwiftUI

/// The Pipeline: every card grouped by who acts next (ADR 0007), as `GET /pipeline` sends it. A tap on a header
/// collapses its group; Archived starts collapsed. A card whose group changed glides to its new place on reload.
struct PipelineView: View {
    let client: APIClient
    let push: Push

    @State private var groups: [PipelineGroup] = []
    @State private var loaded = false
    @State private var error: String?
    @State private var path: [Card] = []
    @State private var query = ""
    @State private var adding = false
    @State private var collapsed: Set<String> = ["archived"]
    @State private var rating: Card?
    @Environment(\.motionReduced) private var motionReduced

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error {
                    ErrorRow(text: error) { await load() }
                }
                // One ForEach for headers and cards, so a card that changes group is the same row, and moves.
                ForEach(rows) { row in
                    switch row {
                    case .header(let group, let count):
                        header(group, count: count)
                    case .card(let card, _):
                        NavigationLink(value: card) {
                            CardRow(card: card) { PipelineStatus(card: card) { rating = card } }
                        }
                    }
                }
            }
            .overlay {
                if loaded && groups.isEmpty && error == nil {
                    ContentUnavailableView(
                        "No cards yet", systemImage: "person.2",
                        description: Text("Matches from a connected app show up here. Add one by hand with the plus button.")
                            .foregroundStyle(.secondaryText)
                    )
                    .fontDesign(.serif)
                }
            }
            .navigationTitle("Pipeline")
            .searchable(text: $query, prompt: "Name")
            .searchToolbarBehavior(.minimize)
            .toolbar {
                Button("Add card", systemImage: "plus") { adding = true }
            }
            .sheet(isPresented: $adding) {
                NewCardSheet(client: client) { _ in Task { await load() } }
            }
            .sheet(item: $rating) { card in
                DateRatingSheet(name: card.name) { stars, note in
                    var rated = card
                    rated.dateRating = stars
                    rated.dateNote = note
                    Task { await save(rated) }
                }
            }
            .navigationDestination(for: Card.self) { card in
                // A change can move the card to another group, so the Pipeline reloads.
                CardDetailView(client: client, card: card) { _ in Task { await load() } }
            }
            .refreshable { await load() }
            .task { await load() }
            // `DCRM_CARD=7` opens that card on launch, for scripted simulator checks (see `Session.init`).
            .task {
                if let id = ProcessInfo.processInfo.environment["DCRM_CARD"].flatMap(Int.init),
                   let card = try? await client.card(id: id) {
                    path = [card]
                }
            }
            // A tapped push replaces whatever is open with its card.
            .task(id: push.openedCardID) {
                if let card = await push.takeOpenedCard(from: client) {
                    path = [card]
                }
            }
        }
    }

    private enum Row: Identifiable {
        case header(PipelineGroup, count: Int)
        case card(Card, id: String)

        var id: String {
            switch self {
            case .header(let group, _): "group-\(group.group)"
            case .card(_, let id): id
            }
        }
    }

    /// Headers and the cards of open groups. A search opens every group and filters the cards by name.
    private var rows: [Row] {
        groups.flatMap { group -> [Row] in
            let cards = group.cards.filter { query.isEmpty || $0.name.localizedStandardContains(query) }
            guard !cards.isEmpty else { return [] }
            let open = !query.isEmpty || !collapsed.contains(group.group)
            // With motion reduced, a card in a new group is a new row: it fades out and in instead of moving.
            let rows = cards.map { Row.card($0, id: motionReduced ? "\(group.group)-\($0.id)" : "card-\($0.id)") }
            return [.header(group, count: cards.count)] + (open ? rows : [])
        }
    }

    private func header(_ group: PipelineGroup, count: Int) -> some View {
        let isCollapsed = query.isEmpty && collapsed.contains(group.group)
        return Button {
            withAnimation(motionReduced ? .easeInOut(duration: 0.2) : .snappy) {
                if collapsed.contains(group.group) { collapsed.remove(group.group) } else { collapsed.insert(group.group) }
            }
        } label: {
            HStack {
                // Only what waits on the user takes the accent.
                Text(group.title)
                    .foregroundStyle(group.group == "waiting_for_you" ? Color.accent : Color.primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text("\(count)").monospacedDigit().foregroundStyle(.secondaryText)
                Image(systemName: "chevron.down")
                    .rotationEffect(.degrees(isCollapsed ? -90 : 0))
                    .foregroundStyle(.secondaryText)
            }
            .font(.headline)
            .frame(minHeight: 44)
            .contentShape(.rect)
        }
        .buttonStyle(.plain)
        .listRowSeparator(.hidden)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(group.title), \(count) \(count == 1 ? "card" : "cards")")
        .accessibilityValue(isCollapsed ? "Collapsed" : "Expanded")
        .accessibilityAddTraits([.isHeader, .isButton])
    }

    private func load() async {
        do {
            let loaded = try await client.pipeline()
            withAnimation(motionReduced ? .easeInOut(duration: 0.25) : .spring(duration: 0.5, bounce: 0.25)) {
                groups = loaded
            }
            error = nil
        } catch {
            self.error = "The Pipeline did not load. Tap to try again."
        }
        loaded = true
    }

    private func save(_ card: Card) async {
        do {
            _ = try await client.update(card)
            await load()
        } catch {
            self.error = "The rating was not saved. Tap to reload, then rate the date again."
        }
    }
}

extension Card {
    /// What the Pipeline row says about the card, from the server's codes; nil for no line. Each group has one
    /// source: the reason, what autopilot is doing, the user's last message, or the next action.
    func pipelineStatus(now: Date = .now, calendar: Calendar = .current) -> String? {
        switch pipelineGroup {
        case "waiting_for_you":
            switch reason {
            case "handover": ["Handover", handoverTrigger.map(Self.triggerTitle)].compactMap { $0 }.joined(separator: " · ")
            case "draft_in_review": "\(pendingDraft?.kind == .opener ? "Opener" : "Reply") ready in Review"
            case "copied_draft": "Copied draft · not sent yet"
            case "failed_send": "Send failed"
            case "stalled": "Stalled · revive or archive"
            case "overdue": nextAction ?? "Next action overdue"
            case "rate_date": "Rate the date"
            case "your_turn": "Your turn"
            case "opener_due": "Send an opener"
            default: nil
            }
        case "handled_by_autopilot":
            autopilotStatus(now: now, calendar: calendar).map { activity in
                // A planned send ends with why its time; without a reason, like the rest, with the topic.
                let why = autopilotActivity == "planned" ? plannedSend?.timingReason.flatMap { $0.isEmpty ? nil : $0 } : nil
                return [activity, why ?? topic.flatMap { $0.isEmpty ? nil : "talking \($0)" }]
                    .compactMap { $0 }.joined(separator: " · ")
            }
        case "waiting_for_them":
            lastMessage.map { "You wrote \(RelativeTime.ago($0.sentAt, now: now, calendar: calendar))" }
        case "texting_off_app":
            nextAction.map { action in dueDate.map { "\(action) · \(RelativeTime.day($0, now: now, calendar: calendar))" } ?? action }
                ?? dateRating.map { "Date rated \($0)/5" } ?? "No next action"
        default:
            dateRating.map { "Date rated \($0)/5" }
        }
    }

    /// What autopilot is doing on the card, in words; nil for an unknown activity.
    private func autopilotStatus(now: Date, calendar: Calendar) -> String? {
        switch autopilotActivity {
        case "writing_opener": "writing an opener"
        case "drafting_reply": "drafting a reply"
        case "planned": plannedSend?.sendAt.map { "replies \(RelativeTime.around($0, now: now, calendar: calendar))" }
        case "sent_waiting": lastMessage.map { "sent \(RelativeTime.ago($0.sentAt, now: now, calendar: calendar)), no reply yet" }
        default: nil
        }
    }

    /// The handover check that hit, in words (`app/jev.py`, `HANDOVER`).
    private static func triggerTitle(_ check: String) -> String {
        switch check {
        case "asks_if_ai": "asked if you're AI"
        case "logistics": "date plans"
        case "place_or_exclusivity": "place or exclusivity"
        case "personal_info": "personal info"
        case "sensitive": "sensitive topic"
        case "unavailable": "not checked"
        default: check.replacing("_", with: " ")
        }
    }
}

/// A Pipeline row's status line, worded by `Card.pipelineStatus`. The AI marker shows where the AI made the draft
/// or is acting; "Rate the date" opens the rating.
private struct PipelineStatus: View {
    let card: Card
    let rate: () -> Void

    var body: some View {
        if let text = card.pipelineStatus() {
            if card.reason == "rate_date" {
                Button(action: rate) {
                    // An HStack, not a Label: in a list row a Label puts the icon in a wide column.
                    HStack(spacing: 4) {
                        Image(systemName: "star")
                        Text(text)
                    }
                    .font(.subheadline.weight(.semibold))
                    .frame(minHeight: 44, alignment: .leading)
                    .contentShape(.rect)
                }
                .buttonStyle(.borderless)
                .accessibilityHint("Opens the rating")
            } else {
                AdaptiveStack {
                    if let marker { AIMarker(marker) }
                    Text(text).font(.subheadline)
                }
            }
        }
    }

    private var marker: AIMarker.Kind? {
        card.pipelineGroup == "handled_by_autopilot" ? .autopilot : card.reason == "draft_in_review" ? .draft : nil
    }
}
