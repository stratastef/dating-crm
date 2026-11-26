import SwiftUI

extension EnvironmentValues {
    /// True when Reduce Motion or Low Power Mode is on: use plain fades, and no springs, rings or color field.
    /// `MainTabView` sets it for the whole app.
    @Entry var motionReduced = false
}

/// Sets `motionReduced` for everything inside. Apply once, at the root.
struct MotionReducedReader: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled

    func body(content: Content) -> some View {
        content
            .environment(\.motionReduced, reduceMotion || lowPower)
            .task {
                for await _ in NotificationCenter.default.notifications(named: .NSProcessInfoPowerStateDidChange) {
                    lowPower = ProcessInfo.processInfo.isLowPowerModeEnabled
                }
            }
    }
}
