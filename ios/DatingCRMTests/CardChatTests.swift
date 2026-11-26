import Foundation
import Testing
@testable import DatingCRM

/// The card detail's Chat tab: the messages with what autopilot sent alone, and the drafts the composer docks.
struct CardChatTests {
    let server = StubServer()

    @Test func readsTheChatWithWhatAutopilotSentAloneAndWhatFiredAHandover() async throws {
        server.respond("""
        [{"id": 7, "card_id": 1, "external_id": "m7", "sender": "them", "body": "where do you live?",
          "sent_at": "2026-11-20T10:00:00.123456Z", "handover": ["personal_info"], "sent_by_autopilot": false},
         {"id": 8, "card_id": 1, "external_id": "m8", "sender": "me", "body": "near the park",
          "sent_at": "2026-11-20T10:05:00Z", "handover": null, "sent_by_autopilot": true}]
        """)

        let messages = try await server.client().messages(cardID: 1)

        #expect(messages.map(\.sentByAutopilot) == [false, true])
        #expect(messages.map(\.handover) == [["personal_info"], nil])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/cards/1/messages")
        #expect(request.httpBody == nil)
    }

    @Test func readsTheDraftsTheCardDocksAndWhenTheyMatched() async throws {
        server.respond("""
        {"id": 1, "app": "hinge", "name": "Ada", "stage": "chatting", "notes": "", "stalled": false, "hot": false,
         "created_at": "2026-11-19T09:00:00.5Z",
         "drafts": [
           {"id": 9, "card_id": 1, "kind": "reply", "status": "pending", "original": "saturday?", "edited": null,
            "guardrail": [], "hot_lead": false, "sendable": false},
           {"id": 8, "card_id": 1, "kind": "reply", "status": "copied", "original": "sunday?", "edited": null,
            "guardrail": [], "hot_lead": false, "sendable": false},
           {"id": 7, "card_id": 1, "kind": "opener", "status": "failed", "original": "hi", "edited": null,
            "guardrail": [], "hot_lead": false, "sendable": true}]}
        """)

        let card = try await server.client().card(id: 1)

        #expect(card.drafts?.map(\.status) == ["pending", "copied", "failed"])
        #expect(card.drafts?.first == Draft(id: 9, kind: .reply, original: "saturday?", edited: nil, guardrail: [], status: "pending"))
        #expect(card.createdAt == Date(timeIntervalSince1970: 1_795_078_800.5))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/cards/1")
    }

    @Test func opensOnChatAndOffersWriteDraftOnlyWhileTheChatIsInTheDatingApp() {
        #expect(Stage.allCases.filter(\.chatsInApp) == [.matched, .chatting])
    }
}
