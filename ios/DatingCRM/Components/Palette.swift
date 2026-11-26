import SwiftUI

// A3 colors (ADR 0009). The app is black and white: `MainTabView` tints buttons, links and the selected tab with
// `.primary`, so the accent never lands on a control by default.
extension ShapeStyle where Self == Color {
    /// Indigo, only for what waits on the user: the Waiting for you header, hot leads, overdue times, the review
    /// count and Today's counter. Never on buttons, links or the selected tab.
    static var accent: Color { Color(light: 0x4F46E5, dark: 0xA5B4FC) }

    /// Behind monograms and accent tiles.
    static var accentSoft: Color { Color(light: 0xEEF0FF, dark: 0x1E1B4B) }

    /// Metadata, times and captions. The system `.secondary` is 3.5:1 on white; this is 5:1 or more.
    static var secondaryText: Color { Color(light: 0x6C6C70, dark: 0x98989F) }
}

private extension Color {
    init(light: UInt32, dark: UInt32) {
        self.init(uiColor: UIColor { $0.userInterfaceStyle == .dark ? UIColor(rgb: dark) : UIColor(rgb: light) })
    }
}

private extension UIColor {
    convenience init(rgb: UInt32) {
        self.init(
            red: CGFloat(rgb >> 16 & 0xFF) / 255, green: CGFloat(rgb >> 8 & 0xFF) / 255, blue: CGFloat(rgb & 0xFF) / 255,
            alpha: 1)
    }
}

/// A capsule in the label color: black in light mode, white in dark. For the one main action of a screen or item.
struct PrimaryCapsuleStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(Color(uiColor: .systemBackground))
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(.primary, in: .capsule)
            .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.4)
    }
}

/// A capsule on the system fill, for the actions next to a primary one.
struct SecondaryCapsuleStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(.primary)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(Color(uiColor: .tertiarySystemFill), in: .capsule)
            .opacity(isEnabled ? (configuration.isPressed ? 0.7 : 1) : 0.4)
    }
}

extension ButtonStyle where Self == PrimaryCapsuleStyle {
    static var primaryCapsule: Self { .init() }
}

extension ButtonStyle where Self == SecondaryCapsuleStyle {
    static var secondaryCapsule: Self { .init() }
}
