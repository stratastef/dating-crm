import Foundation
import Testing
@testable import DatingCRM

struct HandoverTests {
    let server = StubServer()

    @Test func readsACardsHandoverStateAndSuggestedReplies() async throws {
        server.respond("""
        {"id": 1, "app": "tinder", "name": "Ada", "stage": "chatting", "notes": "", "next_action": null,
         "due_date": null, "handover": "taken_over", "handover_suggestions": ["saturday works"], "stalled": false, "hot": false}
        """)

        let card = try await server.client().card(id: 1)

        #expect(card.handover == .takenOver)
        #expect(card.handoverSuggestions == ["saturday works"])
    }

    @Test func readsAHandoverInTheQueueWithItsSuggestedReplies() async throws {
        server.respond("""
        [{"kind": "handover", "hot": true, "card_id": 2, "card_name": "Kim", "draft": null,
          "suggestions": ["saturday works", "sunday?"]}]
        """)

        let items = try await server.client().queue()

        #expect(items == [
            QueueItem(kind: "handover", hot: true, cardID: 2, cardName: "Kim", draft: nil,
                      suggestions: ["saturday works", "sunday?"]),
        ])
    }

    @Test func takesOverAChat() async throws {
        server.respond(#"{"handover": "taken_over", "handover_suggestions": []}"#)

        try await server.client().takeOver(cardID: 7)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/cards/7/take-over")
    }

    @Test func handsAChatBackToAutopilot() async throws {
        server.respond(#"{"handover": null, "handover_suggestions": []}"#)

        try await server.client().handBack(cardID: 7)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/cards/7/hand-back")
    }
}
