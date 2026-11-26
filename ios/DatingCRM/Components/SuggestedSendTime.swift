import SwiftUI

/// When the user's draft is best sent, and why: "Best sent around 20:15 · she's on a roll" (ADR 0008). Nothing once
/// that time has passed. Put it in the draft's `Inset`, where the grey text stays at 4.5:1.
struct SuggestedSendTime: View {
    let draft: Draft

    var body: some View {
        if let at = draft.suggestedSendAt {
            let reason = draft.timingReason.flatMap { $0.isEmpty ? nil : " · \($0)" } ?? ""
            Text("\(Image(systemName: "clock")) Best sent \(RelativeTime.around(at))\(reason)")
                .font(.footnote)
                .foregroundStyle(.secondaryText)
                .fixedSize(horizontal: false, vertical: true)  // wraps, never truncates, in the height-pressed composer
        }
    }
}
