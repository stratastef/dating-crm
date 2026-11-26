import SwiftUI

/// The animated splash (docs/brand/motion-and-haptics.md), over the app on a cold launch only: `DatingCRMApp` keeps it
/// in state that lives as long as the process, so a resume never shows it. The generated launch screen before it is
/// blank paper, so nothing jumps. The hour ring draws clockwise from just past one o'clock, the dot lands at one
/// o'clock, the wordmark rises. With motion reduced, the finished mark shows and leaves in one 300 ms fade.
/// No haptic: it would play on every cold start and mean nothing.
struct Splash: View {
    /// Today's first load is over, or there is no Today to wait for.
    let ready: Bool
    /// Called when the splash should go. `DatingCRMApp` fades it out.
    let finish: () -> Void

    @Environment(\.motionReduced) private var motionReduced
    @State private var shown = ContinuousClock.now
    @State private var ring = 0.0
    @State private var dot = 0.0
    @State private var word = false

    /// The mark's 512 grid, in points.
    private static let size: CGFloat = 120
    /// The ring stops this far either side of the dot: the dot, the ring's round caps and a 3.5° gap.
    private static let gap = 26.87

    var body: some View {
        VStack(spacing: 24) {
            mark
            // shortcut: New York stands in for the wordmark's Newsreader SemiBold, which the app does not bundle.
            Text("goodhour")
                .font(.system(size: 34, weight: .semibold, design: .serif))
                .tracking(-0.68)  // -2%
                .opacity(motionReduced || word ? 1 : 0)
                .offset(y: motionReduced || word ? 0 : 8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background { Color(uiColor: .systemBackground).ignoresSafeArea() }  // paper, as on the launch screen
        .accessibilityHidden(true)
        .task {
            guard !motionReduced else { return }
            withAnimation(.easeInOut(duration: 0.52).delay(0.12)) { ring = 1 }
            withAnimation(.easeOut(duration: 0.18).delay(0.56)) { dot = 1.18 }
            withAnimation(.easeOut(duration: 0.32).delay(0.76)) { word = true }
            try? await Task.sleep(for: .milliseconds(740))
            withAnimation(.spring(duration: 0.18, bounce: 0.45)) { dot = 1 }  // damping 0.55, settled by 920 ms
        }
        .task(id: ready) {
            try? await Task.sleep(for: Self.wait(ready: ready, reduced: motionReduced, elapsed: .now - shown))
            if !Task.isCancelled { finish() }
        }
    }

    /// The hour ring with its dot at one o'clock, on the brand kit's 512 grid: ring radius 168, stroke 56, dot radius 40.
    private var mark: some View {
        let unit = Self.size / 512
        return ZStack {
            Circle()
                .trim(from: 0, to: (360 - 2 * Self.gap) / 360 * (motionReduced ? 1 : ring))
                .stroke(.primary, style: StrokeStyle(lineWidth: 56 * unit, lineCap: .round))
                .rotationEffect(.degrees(30 + Self.gap - 90))  // a circle's trim starts at three o'clock
                .frame(width: 336 * unit, height: 336 * unit)
            Circle()
                .fill(.accent)
                .frame(width: 80 * unit, height: 80 * unit)
                .scaleEffect(motionReduced ? 1 : dot)
                .offset(x: 168 * unit * sin(.pi / 6), y: -168 * unit * cos(.pi / 6))  // one o'clock
        }
        .frame(width: Self.size, height: Self.size)
    }

    /// How much longer the splash stays, `elapsed` after it showed: until the dot has landed (at once with motion
    /// reduced) and Today is ready, and never past the end of the animation. A slower load shows Today's own loading
    /// state instead, so the splash never makes anyone wait.
    static func wait(ready: Bool, reduced: Bool, elapsed: Duration) -> Duration {
        let landed: Duration = reduced ? .zero : .milliseconds(920)
        let end: Duration = .milliseconds(1200)
        return max(min(ready ? max(elapsed, landed) : end, end) - elapsed, .zero)
    }
}

extension EnvironmentValues {
    /// Today calls it once its first load is over, so the splash can hand over. `DatingCRMApp` sets it.
    @Entry var todayLoaded: @MainActor () -> Void = {}
}
