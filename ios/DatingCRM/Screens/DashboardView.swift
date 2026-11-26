import Charts
import SwiftUI

/// The headline, good dates per hour week by week, this month's funnel and this month's AI spend.
struct DashboardView: View {
    let client: APIClient

    @State private var dashboard: Dashboard?
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                ErrorRow(text: error) { await load() }
            }
            if let dashboard {
                DashboardHeadline(dashboard: dashboard)
                if dashboard.weeks.isEmpty {
                    Text("No time or rated dates recorded yet.").fontDesign(.serif).foregroundStyle(.secondaryText)
                } else {
                    Section {
                        // A week with no recorded time has no rate and leaves a gap.
                        Chart(dashboard.weeks.filter { $0.goodDatesPerHour != nil }) { week in
                            LineMark(x: .value("Week", week.week, unit: .weekOfYear), y: .value("Good dates per hour", week.goodDatesPerHour ?? 0))
                            PointMark(x: .value("Week", week.week, unit: .weekOfYear), y: .value("Good dates per hour", week.goodDatesPerHour ?? 0))
                        }
                        .foregroundStyle(Color.primary)
                        // The default axis labels are the system grey, under 4.5:1.
                        .chartXAxis { AxisMarks { _ in AxisGridLine(); AxisValueLabel().foregroundStyle(.secondaryText) } }
                        .chartYAxis { AxisMarks { _ in AxisGridLine(); AxisValueLabel().foregroundStyle(.secondaryText) } }
                        .frame(height: 200)
                        .accessibilityLabel("Good dates per hour by week")
                    } header: {
                        header("Good dates per hour by week")
                    }
                }
                Section {
                    count("Matched", dashboard.funnel.matched)
                    count("Chatting", dashboard.funnel.chatting)
                    count("Date set", dashboard.funnel.dateSet)
                    count("Dated", dashboard.funnel.dated)
                    count("Good", dashboard.funnel.good)
                } header: {
                    header("This month")
                }
                Section {
                    value("Per good date", dashboard.spendPerGoodDateUsd.map(Budget.dollars) ?? "No good date yet")
                    value("Spent this month", dashboard.budget.spentOfCap)
                } header: {
                    header("AI spend")
                }
                if !dashboard.weeks.isEmpty {
                    Section {
                        ForEach(dashboard.weeks.reversed()) { week in
                            VStack(alignment: .leading) {
                                Text("Week of \(week.week.formatted(date: .abbreviated, time: .omitted))").font(.headline)
                                Text(summary(week)).font(.subheadline).foregroundStyle(.secondaryText)
                            }
                        }
                    } header: {
                        header("Weeks")
                    }
                }
            }
        }
        .navigationTitle("Dashboard")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
    }

    private func count(_ stage: String, _ cards: Int) -> some View {
        value(stage, cards.formatted())
    }

    private func value(_ label: String, _ text: String) -> some View {
        LabeledContent(label) {
            Text(text).foregroundStyle(Color.primary)  // the system grey is under 4.5:1
        }
    }

    private func header(_ title: String) -> some View {
        Text(title).foregroundStyle(Color.primary)
    }

    private func summary(_ week: DashboardWeek) -> String {
        let hours = week.hours.formatted(.number.precision(.fractionLength(1)))
        let rate = week.goodDatesPerHour.map { "\($0.formatted(.number.precision(.fractionLength(2)))) per hour" } ?? "no time recorded"
        return "\(week.goodDates) good dates, \(hours) h, \(rate)"
    }

    private func load() async {
        do {
            dashboard = try await client.dashboard()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
