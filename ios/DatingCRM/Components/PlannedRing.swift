import SwiftUI

/// Autopilot's planned send as a `Ring` that drains from when the draft was written to when it goes out, redrawn
/// every second by `TimelineView`. With motion reduced it stays where it was drawn; the time beside it still says
/// when.
struct PlannedRing: View {
    let draft: Draft
    @Environment(\.motionReduced) private var motionReduced

    var body: some View {
        if let sendAt = draft.sendAt {
            if motionReduced {
                Ring(left: Self.left(from: draft.createdAt, to: sendAt, now: .now))
            } else {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    Ring(left: Self.left(from: draft.createdAt, to: sendAt, now: context.date))
                }
            }
        }
    }

    /// The share of the wait still to go, 1 to 0. Full when it is not known when the draft was written.
    static func left(from written: Date?, to sendAt: Date, now: Date) -> Double {
        guard let written, sendAt > written else { return 1 }
        return min(max(sendAt.timeIntervalSince(now) / sendAt.timeIntervalSince(written), 0), 1)
    }
}
