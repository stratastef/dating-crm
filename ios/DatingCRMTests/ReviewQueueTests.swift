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

    @Test func readsWhatEachItemNeedsToDecide() async throws {
        server.respond("""
        [{"kind": "draft", "hot": true, "card_id": 1, "card_name": "Ada",
          "card": {"id": 1, "app": "tinder", "name": "Ada", "stage": "chatting", "notes": "", "stalled": false,
                   "hot": true, "lead_photo_url": "https://photos.test/ada.jpg"},
          "draft": {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "saturday?", "edited": null},
          "message": {"body": "when are you free?", "sent_at": "2026-11-20T10:05:00Z"}, "triggers": null},
         {"kind": "handover", "hot": true, "card_id": 2, "card_name": "Kim", "card": null, "draft": null,
          "message": {"body": "are you a bot?", "sent_at": "2026-11-20T10:00:00Z"}, "triggers": ["asks_if_ai"],
          "suggestions": ["would a bot say that"]},
         {"kind": "paid_item", "hot": false, "card_id": null, "card_name": "Eve", "card": null, "draft": null,
          "message": null, "triggers": null, "suggestions": null,
          "paid_item": {"id": 3, "app": "tinder", "item": "super_like", "name": "Eve", "reason": "She climbs.",
                        "status": "pending", "candidate_id": 8, "photo_url": "https://photos.test/eve.jpg",
                        "cost": "$1.99"}}]
        """)

        let items = try await server.client().queue()

        let sentAt = try Date("2026-11-20T10:05:00Z", strategy: .iso8601)
        #expect(items[0].card?.app == "tinder")
        #expect(items[0].card?.leadPhotoUrl == URL(string: "https://photos.test/ada.jpg"))
        #expect(items[0].message == QuotedMessage(body: "when are you free?", sentAt: sentAt))
        #expect(items[1].triggers == ["asks_if_ai"])
        #expect(items[1].message?.body == "are you a bot?")
        let paid = try #require(items[2].paidItem)
        #expect(paid.candidateID == 8)
        #expect(paid.photoUrl == URL(string: "https://photos.test/eve.jpg"))
        #expect(paid.cost == "$1.99")
    }

    // Dismiss takes a draft out at once; the server hears of it only once Undo is no longer on offer.

    private let oneDraft = """
    [{"kind": "draft", "hot": false, "card_id": 1, "card_name": "Ada",
      "draft": {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "saturday?", "edited": null}}]
    """

    @Test func undoAfterDismissRestoresTheDraftToReviewAndTheServerNeverHearsOfIt() async throws {
        server.respond(oneDraft)
        server.respond(oneDraft)
        let review = ReviewQueue(client: server.client(), undoWindow: .milliseconds(50))
        await review.load()
        let item = try #require(review.items.first)

        let commit = review.dismiss(item)
        #expect(review.items.isEmpty)
        await review.load()  // a refresh meanwhile does not bring it back
        #expect(review.items.isEmpty)
        review.undo(item)
        await commit.value

        #expect(review.items == [item])
        #expect(server.requests.map { $0.url?.path() } == ["/queue", "/queue"])
    }

    @Test func aDismissedDraftReachesTheServerOnceUndoIsNoLongerOffered() async throws {
        server.respond(oneDraft)
        server.respond(#"{"id": 5, "card_id": 1, "kind": "reply", "status": "dismissed", "original": "saturday?", "edited": null}"#)
        let review = ReviewQueue(client: server.client(), undoWindow: .milliseconds(10))
        await review.load()
        let item = try #require(review.items.first)

        await review.dismiss(item).value

        #expect(review.items.isEmpty)
        let request = try #require(server.requests.last)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/dismiss")
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
