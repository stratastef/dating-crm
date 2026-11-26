import SwiftUI

/// A3 row: the face, the name with the time of the last activity, an optional status line, "Chatting · Tinder",
/// and the badges. The Pipeline passes the status line; `CardRow(card:)` has none.
struct CardRow<Status: View>: View {
    let card: Card
    @ViewBuilder let status: Status
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
                status
                AdaptiveStack {
                    // Stacked at accessibility sizes, like the rest of the row, so it never breaks at the dot.
                    Text("\(card.stage.title)\(size.isAccessibilitySize ? "\n" : " · ")\(card.app.capitalized)")
                        .foregroundStyle(.secondaryText)
                        // Next to a badge at accessibility sizes the row otherwise cut it to "Chatting…".
                        .fixedSize(horizontal: false, vertical: true)
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

extension CardRow where Status == EmptyView {
    init(card: Card) {
        self.init(card: card) { EmptyView() }
    }
}
