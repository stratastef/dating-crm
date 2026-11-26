import Foundation
import Testing
@testable import DatingCRM

struct TodayTests {
    let server = StubServer()

    @Test func readsTheReviewSummaryAndTheThreeGroups() async throws {
        server.respond("""
        {"review": {"count": 3, "hot": 1},
         "overdue": [{"kind": "next_action", "due_date": "2026-11-23", "days_late": 2, "starts_at": null,
                      "card": {"id": 1, "app": "tinder", "name": "Clara", "stage": "chatting", "notes": "",
                               "next_action": "Send her the museum link", "stalled": false, "hot": false}}],
         "today": [{"kind": "date", "starts_at": "2026-11-25T18:30:00Z", "due_date": null, "days_late": null,
                    "card": {"id": 2, "app": "hinge", "name": "Priya", "stage": "date_set", "notes": "", "stalled": false, "hot": false}},
                   {"kind": "stalled", "starts_at": null, "due_date": null, "days_late": null,
                    "card": {"id": 3, "app": "tinder", "name": "Iris", "stage": "chatting", "notes": "", "stalled": true, "hot": false}},
                   {"kind": "rate_date", "starts_at": null, "due_date": null, "days_late": null,
                    "card": {"id": 4, "app": "tinder", "name": "Zoe", "stage": "dated", "notes": "", "stalled": false, "hot": false}}],
         "coming_up": []}
        """)

        let today = try await server.client().today()

        #expect(today.review == ReviewSummary(count: 3, hot: 1))
        #expect(today.overdue.map(\.kind) == [.nextAction])
        #expect(today.overdue[0].dueDate == day(2026, 11, 23))
        #expect(today.overdue[0].daysLate == 2)
        #expect(today.overdue[0].card.nextAction == "Send her the museum link")
        #expect(today.today.map(\.kind) == [.date, .stalled, .rateDate])
        #expect(today.today[0].startsAt == Date(timeIntervalSince1970: 1_795_631_400))
        #expect(today.today.map(\.card.id) == [2, 3, 4])
        #expect(today.comingUp.isEmpty)
        #expect(!today.isEmpty)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/today")
    }

    @Test func sendsThePhonesTimeZone() async throws {
        server.respond(#"{"stalled_after_days": 3, "time_zone": "Europe/Berlin"}"#)

        try await server.client().setTimeZone("Europe/Berlin")

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PATCH")
        #expect(request.url?.absoluteString == "https://crm.test/settings")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["time_zone": "Europe/Berlin"] as NSDictionary)
    }
}
