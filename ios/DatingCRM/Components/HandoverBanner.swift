import SwiftUI
import UIKit

/// A card paused for handover, at the end of its chat just above the composer: why autopilot stopped, the match's
/// message that fired it, the suggested replies to copy, then Hand back and Take over. Once the user took over:
/// Hand back only.
struct HandoverBanner: View {
    let client: APIClient
    let card: Card
    let handover: Handover
    /// The match's newest message that hit a handover check; nil when none is loaded.
    let message: Message?
    let copied: () -> Void
    /// Reloads the card after the server took the handover.
    let changed: () async -> Void

    @State private var busy = false
    @State private var error: String?
    /// The last button tapped, which the error's tap tries again: Take over (true) or Hand back.
    @State private var tookOver = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if handover == .takenOver {
                Text("You took over this chat. Autopilot stays out until you hand it back.")
            } else {
                // The symbol inline, not a Label's icon column, which takes a third of the width at accessibility sizes.
                Text("\(Image(systemName: "hand.raised")) \(Self.reason(message?.handover ?? []))")
                    .font(.headline)
                if let message {
                    Text("“\(message.body)”").lineLimit(6)
                }
                if let suggestions = card.handoverSuggestions, !suggestions.isEmpty {
                    Inset {
                        AIMarker(.suggests)
                        ForEach(suggestions, id: \.self) { suggestion in
                            HStack {
                                Text(suggestion).frame(maxWidth: .infinity, alignment: .leading)
                                Button("Copy", systemImage: "doc.on.doc") {
                                    UIPasteboard.general.string = suggestion
                                    copied()
                                }
                                .labelStyle(.iconOnly)
                                .frame(minWidth: 44, minHeight: 44)
                                .accessibilityLabel("Copy “\(suggestion)”")
                            }
                        }
                    }
                }
            }
            if let error {
                ErrorRow(text: error) { await change(takeOver: tookOver) }
            }
            AdaptiveStack(spacing: 8) {
                if handover == .takenOver {
                    Button("Hand back") { Task { await change(takeOver: false) } }
                        .buttonStyle(.primaryCapsule)
                } else {
                    Button("Hand back") { Task { await change(takeOver: false) } }
                        .buttonStyle(.secondaryCapsule)
                    Button("Take over") { Task { await change(takeOver: true) } }
                        .buttonStyle(.primaryCapsule)
                }
            }
            .disabled(busy)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Color(uiColor: .secondarySystemBackground), in: .rect(cornerRadius: 24))
    }

    /// Why autopilot stopped, from the server's trigger codes (`HANDOVER` in `app/jev.py`). Review says it too.
    static func reason(_ triggers: [String]) -> String {
        let reasons = triggers.map { trigger in
            switch trigger {
            case "asks_if_ai": "they asked if you're an AI"
            case "logistics": "they want to make plans"
            case "place_or_exclusivity": "they asked where to meet or about being exclusive"
            case "personal_info": "they shared or asked for personal info"
            case "sensitive": "they brought up something sensitive"
            case "unavailable": "the message could not be checked"
            default: "a handover trigger fired"
            }
        }
        guard !reasons.isEmpty else { return "Autopilot paused this chat" }
        return "Autopilot stopped: \(reasons.formatted())"
    }

    private func change(takeOver: Bool) async {
        busy = true
        tookOver = takeOver
        defer { busy = false }
        do {
            if takeOver {
                try await client.takeOver(cardID: card.id)
            } else {
                try await client.handBack(cardID: card.id)
            }
            error = nil
            await changed()
        } catch {
            self.error = "Not changed. Check your connection, then tap to try again."
        }
    }
}
