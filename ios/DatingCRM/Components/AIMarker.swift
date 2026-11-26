import SwiftUI

/// Marks what the AI made: the sparkles symbol and one of a fixed set of labels. VoiceOver reads the spoken label.
struct AIMarker: View {
    enum Kind {
        case draft, autopilot, suggests

        var title: String {
            switch self {
            case .draft: "AI draft"
            case .autopilot: "Autopilot"
            case .suggests: "AI suggests"
            }
        }

        var spokenLabel: String {
            switch self {
            case .draft: "Draft written by AI"
            case .autopilot: "Done by autopilot"
            case .suggests: "Suggested by AI"
            }
        }
    }

    let kind: Kind

    init(_ kind: Kind) {
        self.kind = kind
    }

    var body: some View {
        // An HStack, not a Label: in a list row a Label puts the icon in a wide column.
        HStack(spacing: 4) {
            Image(systemName: "sparkles")
            Text(kind.title)
        }
        .font(.footnote.weight(.semibold))
        .foregroundStyle(.secondaryText)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(kind.spokenLabel)
    }
}
