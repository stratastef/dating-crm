import SwiftUI

/// Side by side, or stacked at accessibility text sizes: row metadata, so it never wraps into a ragged block,
/// and pairs of buttons, so their labels never break mid-word.
struct AdaptiveStack<Content: View>: View {
    var spacing: CGFloat = 6
    @ViewBuilder let content: Content
    @Environment(\.dynamicTypeSize) private var size

    var body: some View {
        let layout = size.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: spacing)) : AnyLayout(HStackLayout(spacing: spacing))
        layout { content }
    }
}
