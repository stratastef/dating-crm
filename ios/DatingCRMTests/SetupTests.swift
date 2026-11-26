import Foundation
import Testing
@testable import DatingCRM

struct SetupTests {
    let server = StubServer()

    @Test func readsEachSetupStepInOrder() async throws {
        server.respond("""
        [{"step": "dating_apps", "done": true}, {"step": "calendar", "done": false}, {"step": "voice", "done": false},
         {"step": "preferences", "done": true}, {"step": "swipe_layout_and_autonomy", "done": false}]
        """)

        let steps = try await server.client().setup()

        #expect(steps.map(\.step) == [.datingApps, .calendar, .voice, .preferences, .swipeLayoutAndAutonomy])
        #expect(steps.map(\.done) == [true, false, false, true, false])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/setup")
    }

    @Test func dismissesFinishSetup() async throws {
        server.respond(#"{"stalled_after_days": 3, "time_zone": "UTC", "setup_dismissed": true}"#)

        try await server.client().setSetupDismissed(true)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PATCH")
        #expect(request.url?.absoluteString == "https://crm.test/settings")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["setup_dismissed": true] as NSDictionary)
    }

    @Test func readsTodaysSetupSummaryOrItsAbsence() async throws {
        server.respond(#"{"review": {"count": 0, "hot": 0}, "setup": {"steps_left": 3}, "overdue": [], "today": [], "coming_up": []}"#)
        server.respond(#"{"review": {"count": 0, "hot": 0}, "setup": null, "overdue": [], "today": [], "coming_up": []}"#)

        let unfinished = try await server.client().today()
        let dismissed = try await server.client().today()

        #expect(unfinished.setup == SetupSummary(stepsLeft: 3))
        #expect(dismissed.setup == nil)
    }
}
