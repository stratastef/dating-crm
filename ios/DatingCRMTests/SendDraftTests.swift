import Foundation
import Testing
@testable import DatingCRM

struct SendDraftTests {
    let server = StubServer()

    @Test func asksTheServerToSendADraft() async throws {
        server.respond(
            #"{"id": 5, "card_id": 1, "kind": "reply", "status": "approved", "original": "both. badly.", "edited": null}"#,
            status: 202
        )

        try await server.client().sendDraft(draftID: 5)

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/send")
    }

    @Test func aRefusedSendThrowsTheServersStatus() async throws {
        server.respond(#"{"detail": "tinder is paused"}"#, status: 409)

        await #expect(throws: APIError(status: 409)) {
            try await server.client().sendDraft(draftID: 5)
        }
    }
}
