import Foundation
import Testing
@testable import DatingCRM

struct PushTests {
    let server = StubServer()
    let push = Push()

    @Test func registersTheDeviceTokenWithTheServerAsHex() async throws {
        server.respond("", status: 204)
        push.received(deviceToken: Data([0x0a, 0xff, 0x10]))

        await push.register(with: server.client())

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/devices")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer secret")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["token": "0aff10"])
    }

    @Test func registersNothingUntilAppleHasGivenADeviceToken() async {
        await push.register(with: server.client())

        #expect(server.requests.isEmpty)
    }

    @Test func tappingAPushOpensItsCard() async throws {
        server.respond("""
        {"id": 7, "app": "tinder", "external_id": null, "name": "Ada", "stage": "chatting",
         "stage_changed_at": "2026-11-20T10:00:00Z", "notes": "", "next_action": null,
         "due_date": null, "created_at": "2026-11-19T09:00:00Z"}
        """)

        push.opened(userInfo: ["aps": ["alert": ["title": "Hot lead", "body": "Ada replied"]], "card_id": 7])
        let card = await push.takeOpenedCard(from: server.client())

        #expect(card == Card(id: 7, app: "tinder", name: "Ada", stage: .chatting, notes: "", nextAction: nil, dueDate: nil))
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/cards/7")
        // The tap is used up: the card is not opened a second time.
        #expect(await push.takeOpenedCard(from: server.client()) == nil)
        #expect(server.requests.count == 1)
    }

    @Test func tappingAPushWithoutACardOpensNoCard() async {
        push.opened(userInfo: ["aps": ["alert": ["title": "Budget", "body": "Cap reached"]]])

        #expect(await push.takeOpenedCard(from: server.client()) == nil)
        #expect(server.requests.isEmpty)
    }
}
