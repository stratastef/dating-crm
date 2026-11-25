import Foundation
import Testing
@testable import DatingCRM

struct PaidItemTests {
    let server = StubServer()

    @Test func readsAProposedPaidItemInTheQueue() async throws {
        server.respond("""
        [{"kind": "paid_item", "hot": false, "card_id": null, "card_name": "Eve", "draft": null, "suggestions": null,
          "paid_item": {"id": 3, "app": "tinder", "item": "super_like", "name": "Eve",
                        "reason": "She climbs.", "status": "pending"}}]
        """)

        let items = try await server.client().queue()

        let item = PaidItem(id: 3, app: "tinder", item: "super_like", name: "Eve", reason: "She climbs.", status: "pending")
        #expect(items == [
            QueueItem(kind: "paid_item", hot: false, cardID: nil, cardName: "Eve", draft: nil, paidItem: item),
        ])
        #expect(item.title == "Super Like on Tinder")
        #expect(items[0].id == "paid_item-3")
    }

    @Test func approvingAPaidItemTellsWhetherItWasSpent() async throws {
        server.respond(#"{"id": 3, "app": "tinder", "item": "boost", "name": "tinder", "reason": "", "status": "failed"}"#)

        let item = try await server.client().approve(paidItemID: 3)

        #expect(item.status == "failed")
        #expect(item.title == "Boost on Tinder")
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/paid-items/3/approve")
    }

    @Test func declinesAPaidItem() async throws {
        server.respond(#"{"id": 3, "app": "hinge", "item": "rose", "name": "Eve", "reason": "", "status": "declined"}"#)

        try await server.client().decline(paidItemID: 3)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/paid-items/3/decline")
    }
}
