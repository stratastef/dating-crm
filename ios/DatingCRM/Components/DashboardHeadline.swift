import SwiftUI

/// The Dashboard headline: good dates per hour this week, set against the four-week average. You opens with it, and
/// so does `DashboardView`.
struct DashboardHeadline: View {
    let dashboard: Dashboard

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(dashboard.thisWeek.map(Self.rate) ?? "–")
                .font(.largeTitle.bold())
                .monospacedDigit()
                .accessibilityHidden(dashboard.thisWeek == nil)
            Text(dashboard.thisWeek == nil ? "No time recorded this week yet" : "good dates per hour this week")
                .font(.headline)
            Text(dashboard.fourWeekAverage.map { "Four-week average: \(Self.rate($0))" } ?? "No four-week average yet")
                .foregroundStyle(.secondaryText)
            Text("Good = rated 4 or 5.")
                .fontDesign(.serif)
                .foregroundStyle(.secondaryText)
        }
        .padding(.vertical, 8)
        .accessibilityElement(children: .combine)
    }

    private static func rate(_ perHour: Double) -> String {
        perHour.formatted(.number.precision(.fractionLength(2)))
    }
}
