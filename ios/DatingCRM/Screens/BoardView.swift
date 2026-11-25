import SwiftUI

/// The pipeline board: the user's cards under the seven stages.
struct BoardView: View {
    let client: APIClient
    let push: Push
    let signOut: () -> Void

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
                    Section("\(stage.title) (\(cards.count))") {
                        ForEach(cards) { card in
                            NavigationLink(value: card) {
                                CardRow(card: card)
                            }
                        }
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
            .toolbar {
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
        VStack(alignment: .leading) {
            Text(card.name).font(.headline)
            if let nextAction = card.nextAction {
                Text(nextAction).font(.subheadline)
            }
            HStack {
                Text(card.app)
                if let dueDate = card.dueDate {
                    Text("Due \(dueDate.formatted(date: .abbreviated, time: .omitted))")
                }
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
    }
}
