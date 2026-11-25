import Foundation
import Testing
@testable import DatingCRM

struct SwipeTests {
    let server = StubServer()

    static let eve = """
    {"id": 7, "app": "tinder", "name": "Eve", "bio": "Climber.", "photos": ["https://img.test/e1.jpg"],
     "suggestion": "like", "reason": "She climbs.", "source": "model", "decision": null}
    """

    @Test func listsTheCandidatesThatWait() async throws {
        server.respond("[\(Self.eve)]")

        let candidates = try await server.client().swipes()

        #expect(candidates == [
            SwipeCandidate(id: 7, app: "tinder", name: "Eve", bio: "Climber.",
                           photos: [URL(string: "https://img.test/e1.jpg")!],
                           suggestion: .like, reason: "She climbs.", source: "model"),
        ])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/swipes")
    }

    @Test func asksForNewSuggestions() async throws {
        server.respond("[\(Self.eve)]")

        let candidates = try await server.client().suggestSwipes(app: "tinder")

        #expect(candidates.map(\.name) == ["Eve"])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/swipes/tinder/suggestions")
    }

    @Test func sendsTheUsersSwipeAndReportsWhetherTheAppWasReached() async throws {
        server.respond(#"""
        {"id": 7, "app": "tinder", "name": "Eve", "bio": "Climber.", "photos": [], "suggestion": "like",
         "reason": "She climbs.", "source": "model", "decision": "pass", "applied": false}
        """#)

        let applied = try await server.client().swipe(candidateID: 7, .pass)

        #expect(applied == false)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/swipes/7/decision")
        #expect(String(data: try #require(request.httpBody), encoding: .utf8) == #"{"decision":"pass"}"#)
    }
}
