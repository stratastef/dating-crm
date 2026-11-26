import SwiftUI

// The haptics vocabulary (docs/brand/motion-and-haptics.md): one feel per meaning, so the same moment always feels
// the same. Seven system haptics here; the eighth, the hour, is `HourRing`. A haptic answers something the user just
// did, or something happening on the screen they are looking at, and always comes with a visible change. Never for
// autopilot work in the background, the splash, scrolling, navigation or tab switches.
extension SensoryFeedback {
    /// Moving through choices: a rating step, an autonomy level.
    static var tick: Self { .selection }
    /// A small act the user can undo: Hold, Copy, Pass, Undo, Hand back, Dismiss, Clear.
    static var tap: Self { .impact(weight: .light) }
    /// A commit that reaches a match: Send, Send at, Send now, Like, Take over.
    static var press: Self { .impact(weight: .medium) }
    /// A big switch: a pause turned on, approving a paid item.
    static var thud: Self { .impact(weight: .heavy) }
    /// The thing finished: the sign-in code accepted, the last waiting item cleared.
    static var done: Self { .success }
    /// Needs you now, on the screen you're on: a handover fires in the open card.
    static var alert: Self { .warning }
    /// Something failed: a send, a wrong sign-in code, a connector signed out, the AI budget reached.
    static var fail: Self { .error }
}

/// One play of a haptic, for a view whose actions play different ones: set `haptic = Haptic(.press)` in the action
/// and put `.haptic(haptic)` on a view that stays on screen. Each new value plays, even the same one twice in a row.
struct Haptic: Equatable {
    let feedback: SensoryFeedback
    private let id = UUID()

    init(_ feedback: SensoryFeedback) {
        self.feedback = feedback
    }
}

extension View {
    /// Plays `haptic` each time it is set. It follows the iPhone's System Haptics switch.
    func haptic(_ haptic: Haptic?) -> some View {
        sensoryFeedback(trigger: haptic) { _, new in new?.feedback }
    }
}
