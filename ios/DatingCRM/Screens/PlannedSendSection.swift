import SwiftUI

/// Autopilot's planned send on a card: the draft it will send alone, when, and why. Send now and Hold come next (#72).
struct PlannedSendSection: View {
    let draft: Draft

    var body: some View {
        Section {
            AdaptiveStack {
                AIMarker(.autopilot)
                Text(when).font(.subheadline)
            }
            Text(draft.text)
        } header: {
            Text("Planned send").foregroundStyle(Color.primary)  // the system grey is under 4.5:1
        }
    }

    /// "Goes out around 20:15 · they take their time".
    private var when: String {
        let time = draft.sendAt.map { "Goes out \(RelativeTime.around($0))" } ?? "Goes out soon"
        guard let reason = draft.timingReason, !reason.isEmpty else { return time }
        return "\(time) · \(reason)"
    }
}
