import Foundation
import Testing
@testable import DatingCRM

struct DashboardTests {
    let server = StubServer()

    @Test func readsTheWeeklyTrendHeadlineFunnelAndSpend() async throws {
        server.respond("""
        {"weeks": [{"week": "2026-11-02", "good_dates": 1, "hours": 2.0, "good_dates_per_hour": 0.5},
                   {"week": "2026-11-09", "good_dates": 1, "hours": 0.0, "good_dates_per_hour": null}],
         "this_week": null, "four_week_average": 0.25,
         "funnel": {"matched": 12, "chatting": 8, "date_set": 3, "dated": 2, "good": 1},
         "spend_per_good_date_usd": 8.2,
         "budget": {"spend_usd": 8.2, "cap_usd": 30, "paused": false}}
        """)

        let dashboard = try await server.client().dashboard()

        #expect(dashboard == Dashboard(
            weeks: [
                DashboardWeek(week: day(2026, 11, 2), goodDates: 1, hours: 2, goodDatesPerHour: 0.5),
                DashboardWeek(week: day(2026, 11, 9), goodDates: 1, hours: 0, goodDatesPerHour: nil),
            ],
            thisWeek: nil, fourWeekAverage: 0.25,
            funnel: .init(matched: 12, chatting: 8, dateSet: 3, dated: 2, good: 1),
            spendPerGoodDateUsd: 8.2,
            budget: Budget(spendUsd: 8.2, capUsd: 30, paused: false)))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/dashboard")
    }

    @Test func reportsTimeSpentInTheApp() async throws {
        server.respond("", status: 204)

        try await server.client().recordTime(seconds: 90)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/time")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["seconds": 90] as NSDictionary)
    }

    @Test func foregroundTimeIsTheSecondsBetweenBecomingActiveAndLeaving() {
        var timer = ForegroundTimer()
        let start = Date(timeIntervalSince1970: 1_000)

        #expect(timer.phaseChanged(active: true, now: start) == nil)
        // A second "active" while already active does not restart the clock.
        #expect(timer.phaseChanged(active: true, now: start + 30) == nil)
        #expect(timer.phaseChanged(active: false, now: start + 90) == 90)
        // Inactive is followed by background: the same stretch is not reported twice.
        #expect(timer.phaseChanged(active: false, now: start + 95) == nil)
        #expect(timer.phaseChanged(active: true, now: start + 200) == nil)
        #expect(timer.phaseChanged(active: false, now: start + 260) == 60)
    }

    @Test func aStretchUnderOneSecondIsNotReported() {
        var timer = ForegroundTimer()
        let start = Date(timeIntervalSince1970: 1_000)

        _ = timer.phaseChanged(active: true, now: start)

        #expect(timer.phaseChanged(active: false, now: start + 0.4) == nil)
    }
}
