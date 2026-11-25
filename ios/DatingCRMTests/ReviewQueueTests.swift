import Foundation
import Testing
@testable import DatingCRM

struct ReviewQueueTests {
    let server = StubServer()

    @Test func listsTheQueueAndKeepsItemsOfKindsItDoesNotKnow() async throws {
        server.respond("""
        [{"kind": "draft", "hot": true, "card_id": 1, "card_name": "Ada",
          "draft": {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "saturday?", "edited": null}},
         {"kind": "handover", "hot": false, "card_id": 2, "card_name": "Kim", "draft": null}]
        """)

        let items = try await server.client().queue()

        #expect(items == [
            QueueItem(kind: "draft", hot: true, cardID: 1, cardName: "Ada",
                      draft: Draft(id: 5, kind: .reply, original: "saturday?", edited: nil)),
            QueueItem(kind: "handover", hot: false, cardID: 2, cardName: "Kim", draft: nil),
        ])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/queue")
    }

    @Test func approvesADraft() async throws {
        server.respond(#"{"id": 5, "card_id": 1, "kind": "reply", "status": "approved", "original": "saturday?", "edited": null}"#)

        try await server.client().approve(draftID: 5)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/approve")
    }

    @Test func dismissesADraft() async throws {
        server.respond(#"{"id": 5, "card_id": 1, "kind": "reply", "status": "dismissed", "original": "saturday?", "edited": null}"#)

        try await server.client().dismiss(draftID: 5)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/dismiss")
    }
}
