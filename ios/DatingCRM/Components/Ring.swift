import SwiftUI

/// Time left as an accent ring, drawn clockwise from the top: full at 1, gone at 0. The text beside it says
/// what it counts down to, so VoiceOver skips it. `Toast.sending` and `PlannedRing` drain it.
struct Ring: View {
    let left: Double

    var body: some View {
        Circle()
            .trim(from: 0, to: left)
            .stroke(.accent, style: StrokeStyle(lineWidth: 3, lineCap: .round))
            .rotationEffect(.degrees(-90))
            .frame(width: 22, height: 22)
            .accessibilityHidden(true)
    }
}
