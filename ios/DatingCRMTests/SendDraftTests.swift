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

    @Test func aSendWithoutATimeHasNoBody() async throws {
        server.respond(#"{"id": 5}"#, status: 202)

        try await server.client().sendDraft(draftID: 5)

        #expect(server.requests[0].httpBody == nil)
    }

    // Send at: the user's own draft goes out at a time they chose, until they cancel it.

    @Test func sendsADraftAtAChosenTime() async throws {
        server.respond(#"{"id": 5}"#, status: 202)

        try await server.client().sendDraft(draftID: 5, at: Date(timeIntervalSince1970: 1_795_634_100))

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/send")
        let body = try JSONSerialization.jsonObject(with: try #require(request.httpBody)) as? NSDictionary
        #expect(body == ["send_at": "2026-11-25T19:15:00Z"])
    }

    @Test func unschedulesAScheduledSend() async throws {
        server.respond(#"""
        {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "both. badly.", "edited": null,
         "guardrail": [], "hot_lead": false, "sendable": true, "send_at": "2026-11-25T19:15:00Z", "timing_reason": ""}
        """#)

        let draft = try await server.client().unschedule(draftID: 5)

        #expect(draft.status == "pending")
        #expect(draft.sendAt == Date(timeIntervalSince1970: 1_795_634_100))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5/unschedule")
        #expect(request.httpBody == nil)
    }

    @Test func decodesACardsScheduledSend() async throws {
        server.respond(#"""
        {"id": 1, "app": "tinder", "name": "Ada", "stage": "chatting", "notes": "", "stalled": false, "hot": false,
         "pipeline_group": "waiting_for_them",
         "scheduled_send": {"id": 5, "card_id": 1, "kind": "reply", "status": "approved", "original": "both. badly.",
                            "edited": null, "guardrail": [], "hot_lead": false, "sendable": true,
                            "send_at": "2026-11-25T19:15:00.123456Z", "timing_reason": "they take their time"}}
        """#)

        let card = try await server.client().card(id: 1)

        let scheduled = try #require(card.scheduledSend)
        #expect((scheduled.id, scheduled.status) == (5, "approved"))
        #expect(abs(try #require(scheduled.sendAt).timeIntervalSince1970 - 1_795_634_100.123) < 0.001)
    }

    @Test func aRefusedSendThrowsTheServersStatus() async throws {
        server.respond(#"{"detail": "tinder is paused"}"#, status: 409)

        await #expect(throws: APIError(status: 409)) {
            try await server.client().sendDraft(draftID: 5)
        }
    }
}
