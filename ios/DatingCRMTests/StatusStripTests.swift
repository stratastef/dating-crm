import Foundation
import Testing
@testable import DatingCRM

struct StatusStripTests {
    let server = StubServer()

    @Test func readsTheStripsMessagesInTheServersOrder() async throws {
        server.respond(#"""
        [
          {"kind": "paused", "app": null, "resets_at": null},
          {"kind": "paused", "app": "tinder", "resets_at": null},
          {"kind": "budget_reached", "app": null, "resets_at": "2027-01-01T00:00:00Z"},
          {"kind": "connector_alert", "app": "tinder", "resets_at": null}
        ]
        """#)

        let messages = try await server.client().status()

        #expect(messages.map(\.kind) == [.paused, .paused, .budgetReached, .connectorAlert])
        #expect(messages.map(\.app) == [nil, "tinder", nil, "tinder"])
        #expect(messages[2].resetsAt?.timeIntervalSince1970 == 1_798_761_600)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/status")
    }

    // Fail plays when a budget or connector message appears while the app is open; a pause is the user's own doing.

    @Test func failPlaysWhenTheStripStartsToSayTheBudgetIsReachedOrAConnectorSignedOut() {
        let budget = StatusMessage(kind: .budgetReached, app: nil, resetsAt: nil)
        let tinder = StatusMessage(kind: .connectorAlert, app: "tinder", resetsAt: nil)
        let hinge = StatusMessage(kind: .connectorAlert, app: "hinge", resetsAt: nil)
        let paused = StatusMessage(kind: .paused, app: nil, resetsAt: nil)

        #expect(StatusStrip.fails(from: nil, to: budget))
        #expect(StatusStrip.fails(from: paused, to: tinder))
        #expect(StatusStrip.fails(from: tinder, to: hinge))
        #expect(!StatusStrip.fails(from: tinder, to: tinder))
        #expect(!StatusStrip.fails(from: nil, to: paused))
        #expect(!StatusStrip.fails(from: budget, to: nil))
    }

    @Test func nothingStoppingAutopilotIsAnEmptyStrip() async throws {
        server.respond("[]")

        #expect(try await server.client().status().isEmpty)
    }
}
