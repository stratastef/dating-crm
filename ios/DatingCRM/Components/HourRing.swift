import CoreHaptics
import Foundation

/// The hour: the one custom haptic (`HourRing.ahap`), tracing the mark: six light taps rising as the ring draws, then
/// one soft full tap as the dot lands, under 600 ms in all. Only for the brand moment, a date set and a good date
/// rated, so it stays special. Does nothing on hardware without haptics.
enum HourRing {
    static let pattern = Bundle.main.url(forResource: "HourRing", withExtension: "ahap")

    private static var engine: CHHapticEngine?

    static func play() {
        guard CHHapticEngine.capabilitiesForHardware().supportsHaptics, let pattern else { return }
        do {
            if engine == nil {
                engine = try CHHapticEngine()
                engine?.playsHapticsOnly = true
            }
            // Before every play: this restarts the engine after a reset, or after iOS stopped it in the background.
            try engine?.start()
            try engine?.playPattern(from: pattern)
        } catch {
            engine = nil  // made anew on the next play
        }
    }
}
