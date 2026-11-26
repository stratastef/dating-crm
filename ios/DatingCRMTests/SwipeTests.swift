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

    @Test func readsAgeDistanceAndTheProposedSuperLike() async throws {
        server.respond(#"""
        [{"id": 7, "app": "tinder", "name": "Eve", "bio": "", "photos": [], "age": 30, "distance_mi": 5,
          "suggestion": "like", "reason": "She climbs.", "source": "model", "decision": null,
          "paid_item": {"id": 3, "app": "tinder", "item": "super_like", "name": "Eve", "reason": "She climbs.",
                        "status": "pending"}}]
        """#)

        let eve = try #require(try await server.client().swipes().first)

        #expect(eve.age == 30)
        #expect(eve.distanceMi == 5)
        #expect(eve.paidItem == PaidItem(id: 3, app: "tinder", item: "super_like", name: "Eve", reason: "She climbs.",
                                         status: "pending"))
    }

    // Swipe layout.

    @Test func readsTheSwipeLayoutAsNilUntilTheUserChooses() async throws {
        server.respond(#"{"layout": null}"#)
        server.respond(#"{"layout": "list"}"#)

        #expect(try await server.client().swipeLayout() == nil)
        #expect(try await server.client().swipeLayout() == .list)
        #expect(server.requests.map(\.httpMethod) == ["GET", "GET"])
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/swipes/layout")
    }

    @Test func savesTheSwipeLayout() async throws {
        server.respond(#"{"layout": "one_at_a_time"}"#)

        let layout = try await server.client().setSwipeLayout(.oneAtATime)

        #expect(layout == .oneAtATime)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/swipes/layout")
        #expect(String(data: try #require(request.httpBody), encoding: .utf8) == #"{"layout":"one_at_a_time"}"#)
    }

    // Undo: a swipe waits in the app until the toast is gone, so Undo leaves nothing on the dating app.

    static let liked = """
    {"id": 7, "app": "tinder", "name": "Eve", "bio": "", "photos": [], "suggestion": "like", "reason": "",
     "source": "model", "decision": "like", "applied": true}
    """

    @MainActor @Test func undoBeforeTheSwipeIsSentSendsNothing() async throws {
        server.respond(Self.liked)  // only so that a swipe sent by mistake fails the test instead of crashing it
        let client = server.client()
        let held = Held(after: .milliseconds(50)) { _ = try? await client.swipe(candidateID: 7, .like) }

        #expect(held.undo())
        try await Task.sleep(for: .milliseconds(200))

        #expect(server.requests.isEmpty)
    }

    @MainActor @Test func aSwipeNotTakenBackIsSentOnceTheWaitIsOver() async throws {
        server.respond(Self.liked)
        let client = server.client()
        let held = Held(after: .milliseconds(50)) { _ = try? await client.swipe(candidateID: 7, .like) }

        // A busy CI runner can take seconds: wait for the send instead of guessing how long it takes.
        for _ in 0..<250 where server.requests.isEmpty { try await Task.sleep(for: .milliseconds(20)) }

        #expect(server.requests.map(\.url?.absoluteString) == ["https://crm.test/swipes/7/decision"])
        #expect(!held.undo())  // too late: it is on the dating app
    }
}
