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

    @Test func takesBackASendTheServerStillHolds() async throws {
        server.respond(#"""
        {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "both. badly.",
         "edited": "both, badly", "guardrail": [], "hot_lead": false, "sendable": true}
        """#)

        let draft = try await server.client().undoSend(draftID: 5)

        #expect(draft == Draft(id: 5, kind: .reply, original: "both. badly.", edited: "both, badly", guardrail: [], sendable: true))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/undo-send")
        #expect(request.httpBody == nil)
    }

    @Test func anUndoAfterTheSendStartedThrowsTheServersStatus() async throws {
        server.respond(#"{"detail": "the draft is sending"}"#, status: 409)

        await #expect(throws: APIError(status: 409)) {
            _ = try await server.client().undoSend(draftID: 5)
        }
    }

    @Test func aRefusedSendThrowsTheServersStatus() async throws {
        server.respond(#"{"detail": "tinder is paused"}"#, status: 409)

        await #expect(throws: APIError(status: 409)) {
            try await server.client().sendDraft(draftID: 5)
        }
    }
}
