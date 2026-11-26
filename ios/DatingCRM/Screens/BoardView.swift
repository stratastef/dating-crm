import SwiftUI

/// The pipeline board: the user's cards under the seven stages.
struct BoardView: View {
    let client: APIClient
    let push: Push

    @State private var cards: [Card] = []
    @State private var error: String?
    @State private var path: [Card] = []

    var body: some View {
        NavigationStack(path: $path) {
            List {
                if let error {
                    Text(error).foregroundStyle(.red)
                }
                ForEach(Stage.allCases) { stage in
                    let cards = cards.filter { $0.stage == stage }
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

private struct CardRow: View {
    let card: Card

    var body: some View {
        HStack(spacing: 14) {
            Avatar(name: card.name, photo: nil)
            VStack(alignment: .leading, spacing: 2) {
                Text(card.name).font(.headline)
                if let nextAction = card.nextAction {
                    Text(nextAction).font(.subheadline)
                }
                AdaptiveStack {
                    Text(card.app.capitalized).foregroundStyle(.secondaryText)
                    if let dueDate = card.dueDate {
                        let days = RelativeTime.daysFrom(.now, to: dueDate)
                        if days < 0 {
                            Badge(.overdue(days: -days))
                        } else {
                            Text("Due \(RelativeTime.day(dueDate))").foregroundStyle(.secondaryText)
                        }
                    }
                }
                .font(.footnote)
            }
        }
    }
}
