import SwiftUI

/// Send at: the user's draft goes out at its suggested send time, with no Undo wait. Next to Send. The label shows
/// the time, which `SuggestedSendTime` above it dates; VoiceOver reads the day too.
struct SendAtButton: View {
    let at: Date
    let action: () -> Void

    var body: some View {
        Button("Send at \(at.formatted(date: .omitted, time: .shortened))", action: action)
            .buttonStyle(.secondaryCapsule)
            .accessibilityLabel("Send \(RelativeTime.at(at))")
    }
}
