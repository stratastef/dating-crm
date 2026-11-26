import SwiftUI
import UIKit

/// A card that autopilot paused for handover: the suggested replies, and the button to take the chat over or
/// hand it back. Shows nothing while `state` is nil.
struct HandoverSection: View {
    let client: APIClient
    let cardID: Int
    var title = "Handover"
    let suggestions: [String]
    /// Set after the server accepted a take-over (`.takenOver`) or a hand-back (nil).
    @Binding var state: Handover?

    @State private var busy = false
    @State private var error: String?

    var body: some View {
        if let state {
            Section(title) {
                if let error {
                    Text(error).foregroundStyle(.red)
                }
                Text(state == .takenOver
                    ? "You took over this chat. Autopilot stays out until you hand it back."
                    : "Autopilot paused this chat. It waits for your reply.")
                    .foregroundStyle(.secondaryText)
                ForEach(suggestions, id: \.self) { suggestion in
                    Button(suggestion, systemImage: "doc.on.doc") {
                        UIPasteboard.general.string = suggestion
                    }
                }
                if state == .takenOver {
                    Button("Hand back to autopilot", systemImage: "arrow.uturn.backward") { change(to: nil) }
                } else {
                    Button("Take over", systemImage: "hand.raised") { change(to: .takenOver) }
                }
            }
            // Without this, a tap anywhere in a row triggers every button in it.
            .buttonStyle(.borderless)
            .disabled(busy)
        }
    }

    private func change(to new: Handover?) {
        busy = true
        Task {
            defer { busy = false }
            do {
                if new == nil {
                    try await client.handBack(cardID: cardID)
                } else {
                    try await client.takeOver(cardID: cardID)
                }
                error = nil
                state = new
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
