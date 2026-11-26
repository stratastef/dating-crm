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

    @Test func nothingStoppingAutopilotIsAnEmptyStrip() async throws {
        server.respond("[]")

        #expect(try await server.client().status().isEmpty)
    }
}
