import SwiftUI

// PROTOTYPE (branch prototype/pipeline-board, never merge): three variants of the Pipeline screen on the
// existing board, switched by a floating bar that exists only in Debug builds. The choice is kept in
// @AppStorage. A: collapsible stage sections. B: rows grouped by who acts next. C: A with B's status line.

/// The pipeline board: the user's cards under the seven stages.
struct BoardView: View {
    let client: APIClient
    let push: Push
    let signOut: () -> Void

    @State private var cards: [Card] = []
    @State private var facts = PipelineFacts()
    @State private var error: String?
    @State private var path: [Card] = []
    @AppStorage("prototype.pipelineVariant") private var variant = PipelineVariant.stages.rawValue

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                switch PipelineVariant(rawValue: variant) ?? .stages {
                case .stages: StageSectionsVariant(cards: cards, facts: facts, statusLine: false)
                case .agent: AgentStatusVariant(cards: cards, facts: facts)
                case .stagesWithStatus: StageSectionsVariant(cards: cards, facts: facts, statusLine: true)
                }
            }
            .safeAreaInset(edge: .top) {
                if let error {
                    Text(error).foregroundStyle(.red).padding(.horizontal)
                }
            }
            #if DEBUG
            .safeAreaInset(edge: .bottom) { VariantSwitcher(variant: $variant) }
            #endif
            .navigationTitle("Pipeline")
            .navigationDestination(for: Card.self) { card in
                CardDetailView(client: client, card: card) { saved in
                    if let index = cards.firstIndex(where: { $0.id == saved.id }) {
                        cards[index] = saved
                    }
                }
            }
            .toolbar {
                NavigationLink("Review") { QueueView(client: client) }
                NavigationLink("Swipe") { SwipeView(client: client) }
                NavigationLink("Dashboard") { DashboardView(client: client) }
                NavigationLink("Preferences") { PreferencesView(client: client) }
                NavigationLink("Photos") { PhotosView(client: client) }
                NavigationLink("Settings") { SettingsView(client: client, apps: Set(cards.map(\.app)).sorted()) }
                Button("Sign out", action: signOut)
            }
            .refreshable { await load() }
            .task { await load() }
            // A tapped push replaces whatever is open with its card.
            .task(id: push.openedCardID) {
                if let card = await push.takeOpenedCard(from: client) {
                    path = [card]
                }
            }
        }
    }

    private func load() async {
        do {
            async let queue = client.queue()
            let loaded = try await client.cards()
            // prototype: one chat call per card for the last message; the real screen needs it on GET /cards.
            var last: [Int: Message] = [:]
            try await withThrowingTaskGroup(of: (Int, Message?).self) { group in
                for card in loaded {
                    group.addTask { [client] in (card.id, try await client.messages(cardID: card.id).last) }
                }
                for try await (id, message) in group {
                    last[id] = message
                }
            }
            facts = PipelineFacts(lastMessage: last, queue: try await queue)
            cards = loaded
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Variants

private enum PipelineVariant: String, CaseIterable {
    case stages = "A", agent = "B", stagesWithStatus = "C"

    var title: String {
        switch self {
        case .stages: "Stage sections"
        case .agent: "Agent status"
        case .stagesWithStatus: "Stages + status line"
        }
    }
}

/// Variant A (and C): one collapsible section per stage, Archived collapsed.
private struct StageSectionsVariant: View {
    let cards: [Card]
    let facts: PipelineFacts
    /// C: the row's line is B's "who acts next" status instead of the last message.
    let statusLine: Bool

    @State private var collapsed: Set<Stage> = [.archived]

    var body: some View {
        List {
            ForEach(Stage.allCases) { stage in
                let inStage = facts.sorted(cards.filter { $0.stage == stage })
                Section(isExpanded: expanded(stage)) {
                    ForEach(inStage) { card in
                        NavigationLink(value: card) {
                            PipelineRow(
                                card: card,
                                time: facts.lastActivity(card).map(ago),
                                line: statusLine ? facts.status(of: card).text : facts.messageLine(card),
                                caption: nil,
                                badges: facts.badges(card)
                            )
                        }
                    }
                } header: {
                    HStack {
                        Text(stage.title)
                        Spacer()
                        Text("\(inStage.count)").monospacedDigit().foregroundStyle(.secondary)
                    }
                }
            }
        }
        .listStyle(.sidebar)
    }

    private func expanded(_ stage: Stage) -> Binding<Bool> {
        Binding(
            get: { !collapsed.contains(stage) },
            set: { if $0 { collapsed.remove(stage) } else { collapsed.insert(stage) } }
        )
    }
}

/// Variant B: rows grouped by who acts next. The stage is secondary, in the caption.
private struct AgentStatusVariant: View {
    let cards: [Card]
    let facts: PipelineFacts

    @State private var collapsed: Set<WhoActs> = [.archived]

    var body: some View {
        List {
            ForEach(WhoActs.allCases, id: \.self) { actor in
                let group = facts.sorted(cards.filter { facts.status(of: $0).actor == actor })
                if !group.isEmpty {
                    Section(isExpanded: expanded(actor)) {
                        ForEach(group) { card in
                            NavigationLink(value: card) {
                                PipelineRow(
                                    card: card,
                                    time: facts.lastActivity(card).map(ago),
                                    line: facts.status(of: card).text,
                                    caption: "\(card.stage.title) · \(card.app.capitalized)",
                                    badges: facts.badges(card)
                                )
                            }
                        }
                    } header: {
                        HStack {
                            Text(actor.title).foregroundStyle(actor == .you ? AnyShapeStyle(.tint) : AnyShapeStyle(.primary))
                            Spacer()
                            Text("\(group.count)").monospacedDigit().foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .listStyle(.sidebar)
    }

    private func expanded(_ actor: WhoActs) -> Binding<Bool> {
        Binding(
            get: { !collapsed.contains(actor) },
            set: { if $0 { collapsed.remove(actor) } else { collapsed.insert(actor) } }
        )
    }
}

// MARK: - Row

private struct PipelineRow: View {
    let card: Card
    let time: String?
    let line: Text
    let caption: String?
    let badges: [RowBadge]

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(card.name.prefix(1))
                .font(.headline)
                .frame(width: 40, height: 40)
                .background(.quaternary, in: .circle)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(card.name).font(.headline)
                    Spacer()
                    if let time {
                        Text(time).font(.subheadline).monospacedDigit().foregroundStyle(.secondary)
                    }
                }
                line.font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
                if let caption {
                    Text(caption).font(.caption).foregroundStyle(.secondary)
                }
                if !badges.isEmpty {
                    HStack(spacing: 6) {
                        ForEach(badges, id: \.text) { BadgeView(badge: $0) }
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}

/// A labeled badge: icon plus text, so it never relies on color alone. `needsYou` tints the icon with the accent.
private struct RowBadge {
    let text: String
    let symbol: String
    let needsYou: Bool
}

private struct BadgeView: View {
    let badge: RowBadge

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: badge.symbol).foregroundStyle(badge.needsYou ? AnyShapeStyle(.tint) : AnyShapeStyle(.secondary))
            Text(badge.text).foregroundStyle(.primary)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(.quaternary, in: .capsule)
    }
}

// MARK: - Data the variants derive

/// Who acts next on a card, in the order variant B lists the groups.
private enum WhoActs: CaseIterable {
    case autopilot, you, offApp, archived

    var title: String {
        switch self {
        case .autopilot: "Autopilot is handling"
        case .you: "Waiting for you"
        case .offApp: "You're texting off-app"
        case .archived: "Archived"
        }
    }
}

private struct CardStatus {
    let actor: WhoActs
    let text: Text
}

/// prototype: what the variants need beyond GET /cards, gathered from GET /queue and each chat.
private struct PipelineFacts {
    var lastMessage: [Int: Message] = [:]
    var queue: [QueueItem] = []

    func isHot(_ card: Card) -> Bool {
        queue.contains { $0.cardID == card.id && $0.hot }
    }

    func pendingDraft(_ card: Card) -> Draft? {
        queue.first { $0.cardID == card.id && $0.kind == "draft" }?.draft
    }

    // prototype: no route lists copied drafts; in the seed Maya's draft was copied and not yet sent.
    func hasCopiedDraft(_ card: Card) -> Bool {
        card.name == "Maya Lindqvist"
    }

    func lastActivity(_ card: Card) -> Date? {
        timestamp(lastMessage[card.id]?.sentAt) ?? timestamp(card.stageChangedAt)
    }

    /// Hot first, then the most recent activity.
    func sorted(_ cards: [Card]) -> [Card] {
        cards.sorted {
            if isHot($0) != isHot($1) { return isHot($0) }
            return (lastActivity($0) ?? .distantPast) > (lastActivity($1) ?? .distantPast)
        }
    }

    func badges(_ card: Card) -> [RowBadge] {
        var badges: [RowBadge] = []
        if isHot(card) { badges.append(RowBadge(text: "Hot", symbol: "flame.fill", needsYou: true)) }
        if card.stalled == true { badges.append(RowBadge(text: "Stalled", symbol: "pause.circle", needsYou: false)) }
        if let days = overdueDays(card) {
            badges.append(RowBadge(text: "Overdue \(days)d", symbol: "exclamationmark.circle", needsYou: true))
        }
        return badges
    }

    /// Variant A's line: the last message, else the next action, else nothing yet.
    func messageLine(_ card: Card) -> Text {
        if let last = lastMessage[card.id] {
            return Text(last.sender == .me ? "You: \(last.body)" : last.body)
        }
        if let action = card.nextAction {
            return Text(card.dueDate.map { "\(action) · due \(dueText($0))" } ?? action)
        }
        return Text("No messages yet")
    }

    /// Variant B's grouping and line: who acts next and what they are doing.
    func status(of card: Card) -> CardStatus {
        let firstName = card.name.split(separator: " ").first.map(String.init) ?? card.name
        if card.stage == .archived {
            return CardStatus(actor: .archived, text: Text(card.dateRating.map { "Date rated \($0)/5" } ?? "Archived"))
        }
        if card.handover == .pending {
            return CardStatus(actor: .you, text: Text("Handover · \(card.nextAction ?? "autopilot stopped")"))
        }
        if let draft = pendingDraft(card) {
            let kind = draft.kind == .opener ? "Opener" : "Reply"
            return CardStatus(actor: .you, text: ai("\(kind) ready in Review"))
        }
        if hasCopiedDraft(card) {
            return CardStatus(actor: .you, text: Text("Copied draft · not sent yet"))
        }
        switch card.stage {
        case .numberSwapped, .dateSet, .dated, .seeingThem:
            let line = card.nextAction.map { action in card.dueDate.map { "\(action) · \(dueText($0))" } ?? action }
                ?? card.dateRating.map { "Date rated \($0)/5" }
                ?? "No next action"
            return CardStatus(actor: .offApp, text: Text(line))
        case .matched, .chatting, .archived:
            // prototype: the seed's chat autonomy is Copilot; this pretends it is Autopilot.
            guard let last = lastMessage[card.id], let sent = timestamp(last.sentAt) else {
                return CardStatus(actor: .autopilot, text: ai("Autopilot · writing an opener"))
            }
            let topic = Self.fakeTopics[firstName].map { " · talking \($0)" } ?? ""
            let line = last.sender == .me
                ? "Autopilot · sent \(ago(sent)) ago, no reply yet\(topic)"
                : "Autopilot · drafting a reply to \(firstName)\(topic)"
            return CardStatus(actor: .autopilot, text: ai(line))
        }
    }

    // prototype: topic summaries are invented; the server has no such field.
    private static let fakeTopics = ["Lena": "her tortoise", "Clara": "museums"]

    private func ai(_ line: String) -> Text {
        Text("\(Image(systemName: "sparkles")) \(line)")
    }

    private func overdueDays(_ card: Card) -> Int? {
        guard let due = card.dueDate else { return nil }
        let today = Calendar.current.startOfDay(for: .now)
        let days = Calendar.current.dateComponents([.day], from: due, to: today).day ?? 0
        return days > 0 ? days : nil
    }
}

/// "10m", "4h", "3d".
private func ago(_ date: Date) -> String {
    let seconds = max(0, Int(Date.now.timeIntervalSince(date)))
    switch seconds {
    case ..<60: return "now"
    case ..<3600: return "\(seconds / 60)m"
    case ..<86400: return "\(seconds / 3600)h"
    default: return "\(seconds / 86400)d"
    }
}

/// "today", "tomorrow", else the weekday: "Fri".
private func dueText(_ date: Date) -> String {
    if Calendar.current.isDateInToday(date) { return "today" }
    if Calendar.current.isDateInTomorrow(date) { return "tomorrow" }
    return date.formatted(.dateTime.weekday(.abbreviated))
}

// shortcut: drops fractional seconds and assumes UTC, which is what the server sends.
private func timestamp(_ text: String?) -> Date? {
    guard let text, text.count >= 19 else { return nil }
    return try? Date(String(text.prefix(19)) + "Z", strategy: .iso8601)
}

// MARK: - Debug-only switcher

#if DEBUG
/// prototype: flips between the Pipeline variants. Not part of the design being judged.
private struct VariantSwitcher: View {
    @Binding var variant: String

    var body: some View {
        let all = PipelineVariant.allCases
        let current = PipelineVariant(rawValue: variant) ?? .stages
        let index = all.firstIndex(of: current) ?? 0
        HStack(spacing: 0) {
            Button {
                variant = all[(index + all.count - 1) % all.count].rawValue
            } label: {
                Image(systemName: "chevron.left").frame(width: 44, height: 44)
            }
            .accessibilityLabel("Previous variant")
            Text("\(current.rawValue) · \(current.title)")
                .font(.footnote.monospaced().weight(.semibold))
                .frame(minWidth: 190)
            Button {
                variant = all[(index + 1) % all.count].rawValue
            } label: {
                Image(systemName: "chevron.right").frame(width: 44, height: 44)
            }
            .accessibilityLabel("Next variant")
        }
        .foregroundStyle(.white)
        .background(.black, in: .capsule)
        .overlay(Capsule().strokeBorder(.yellow, lineWidth: 2))
        .shadow(radius: 8)
        .padding(.bottom, 8)
    }
}
#endif
