import Charts
import SwiftUI

/// Good dates per hour of the user's time, week by week.
struct DashboardView: View {
    let client: APIClient

    @State private var weeks: [DashboardWeek] = []
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            if weeks.isEmpty, error == nil {
                Text("No time or rated dates recorded yet.").foregroundStyle(.secondaryText)
            } else {
                Section("Good dates per hour") {
                    // A week with no recorded time has no rate and leaves a gap.
                    Chart(weeks.filter { $0.goodDatesPerHour != nil }) { week in
                        LineMark(x: .value("Week", week.week, unit: .weekOfYear), y: .value("Good dates per hour", week.goodDatesPerHour ?? 0))
                        PointMark(x: .value("Week", week.week, unit: .weekOfYear), y: .value("Good dates per hour", week.goodDatesPerHour ?? 0))
                    }
                    .frame(height: 200)
                    .accessibilityLabel("Good dates per hour by week")
                }
                Section("Weeks") {
                    ForEach(weeks.reversed()) { week in
                        VStack(alignment: .leading) {
                            Text("Week of \(week.week.formatted(date: .abbreviated, time: .omitted))").font(.headline)
                            Text(summary(week)).font(.subheadline).foregroundStyle(.secondaryText)
                        }
                    }
                }
            }
        }
        .navigationTitle("Dashboard")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func summary(_ week: DashboardWeek) -> String {
        let hours = week.hours.formatted(.number.precision(.fractionLength(1)))
        let rate = week.goodDatesPerHour.map { "\($0.formatted(.number.precision(.fractionLength(2)))) per hour" } ?? "no time recorded"
        return "\(week.goodDates) good dates, \(hours) h, \(rate)"
    }

    private func load() async {
        do {
            weeks = try await client.dashboard()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
