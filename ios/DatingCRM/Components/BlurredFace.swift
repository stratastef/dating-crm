import SwiftUI

/// Blur photos (ADR 0009): with the setting on, a face stays blurred until tapped. Put it on the loaded image,
/// inside the frame's clip, so the blur does not spill out. While blurred, a tap reveals instead of reaching the row.
struct BlurredFace: ViewModifier {
    /// The server holds the setting; the app keeps this copy so every face reads it. `MainTabView` refreshes it on
    /// launch and `PrivacyView` on each change.
    static let key = "blurPhotos"

    @AppStorage(key) private var blurPhotos = false
    @State private var shown = false

    func body(content: Content) -> some View {
        let hidden = blurPhotos && !shown
        content
            .blur(radius: hidden ? 30 : 0, opaque: true)
            .animation(.easeOut(duration: 0.2), value: hidden)  // a fade, fine with Reduce Motion
            .contentShape(.rect)
            .highPriorityGesture(TapGesture().onEnded { shown = true }, including: hidden ? .all : .subviews)
    }
}

extension View {
    func blurredFace() -> some View { modifier(BlurredFace()) }
}
