import SwiftUI

/// The pipeline board: the user's cards under the seven stages.
struct BoardView: View {
    let client: APIClient
    let push: Push

    @State private var cards: [Card] = []
    @State private var error: String?
    @State private var path: [Card] = []
    @State private var query = ""
    @State private var adding = false

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error {
                    Text(error).foregroundStyle(.red)
                }
                ForEach(Stage.allCases) { stage in
                    let cards = cards.filter { $0.stage == stage && (query.isEmpty || $0.name.localizedStandardContains(query)) }
                    Section {
                        ForEach(cards) { card in
                            NavigationLink(value: card) {
                                CardRow(card: card)
                            }
                        }
                    } header: {
                        // The system's grey header is under 4.5:1 contrast.
                        Text("\(stage.title) (\(cards.count))").foregroundStyle(Color.primary)
                    }
                }
            }
            .navigationTitle("Pipeline")
            .searchable(text: $query, prompt: "Name")
            .searchToolbarBehavior(.minimize)
            .toolbar {
                Button("Add card", systemImage: "plus") { adding = true }
            }
            .sheet(isPresented: $adding) {
                NewCardSheet(client: client) { cards.append($0) }
            }
            .navigationDestination(for: Card.self) { card in
                CardDetailView(client: client, card: card) { saved in
                    if let index = cards.firstIndex(where: { $0.id == saved.id }) {
                        cards[index] = saved
                    }
                }
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
            cards = try await client.cards()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// A3 row: the face, the name with the time of the last activity, "Chatting · Tinder", and the badges.
private struct CardRow: View {
    let card: Card
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        HStack(spacing: 14) {
            Avatar(name: card.name, photo: card.leadPhotoUrl)
            VStack(alignment: .leading, spacing: 2) {
                AdaptiveStack {
                    // Full width, so the time sits at the trailing edge, or under the name at accessibility sizes.
                    Text(card.name).font(.headline).frame(maxWidth: .infinity, alignment: .leading)
                    if let time = card.lastActivity {
                        TimeAgoText(date: time).font(.subheadline).foregroundStyle(.secondaryText)
                    }
                }
                AdaptiveStack {
                    // Stacked at accessibility sizes, like the rest of the row, so it never breaks at the dot.
                    Text("\(card.stage.title)\(size.isAccessibilitySize ? "\n" : " · ")\(card.app.capitalized)")
                        .foregroundStyle(.secondaryText)
                    if card.hot { Badge(.hot) }
                    if card.stalled { Badge(.stalled) }
                    if let days = overdueDays { Badge(.overdue(days: days)) }
                }
                .font(.footnote)
            }
        }
    }

    /// Days past the due day; nil when there is no due day or it has not passed. Due today is not overdue.
    private var overdueDays: Int? {
        guard let dueDate = card.dueDate else { return nil }
        let days = -RelativeTime.daysFrom(.now, to: dueDate)
        return days > 0 ? days : nil
    }
}
