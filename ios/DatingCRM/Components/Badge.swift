import SwiftUI

/// A row badge: always an icon and a text label, never color alone.
struct Badge: View {
    enum Kind: Hashable {
        case hot, stalled
        case overdue(days: Int)
    }

    let kind: Kind

    init(_ kind: Kind) {
        self.kind = kind
    }

    var body: some View {
        // An HStack, not a Label: in a list row a Label puts the icon in a wide column.
        HStack(spacing: 3) {
            Image(systemName: symbol)
            Text(title)
        }
        .font(.footnote.weight(.semibold))
        // Hot and Overdue wait on the user; Stalled only asks for a decision some time.
        .foregroundStyle(kind == .stalled ? Color.secondaryText : Color.accent)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenLabel)
    }

    private var title: String {
        switch kind {
        case .hot: "Hot"
        case .stalled: "Stalled"
        case .overdue(let days): "Overdue \(days)d"
        }
    }

    private var spokenLabel: String {
        switch kind {
        case .hot: "Hot lead"
        case .stalled: "Stalled"
        case .overdue(let days): "Overdue \(days) \(days == 1 ? "day" : "days")"
        }
    }

    private var symbol: String {
        switch kind {
        case .hot: "flame.fill"
        case .stalled: "pause.circle"
        case .overdue: "exclamationmark.circle"
        }
    }
}
