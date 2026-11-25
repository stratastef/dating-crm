import Foundation
import Testing
@testable import DatingCRM

struct APIClientTests {
    let server = StubServer()

    @Test func listsTheUsersCardsWithTheBearerToken() async throws {
        server.respond("""
        [{"id": 1, "app": "tinder", "external_id": null, "name": "Ada", "stage": "number_swapped",
          "stage_changed_at": "2026-11-20T10:00:00.123456Z", "notes": "Climbs", "next_action": "Call",
          "due_date": "2026-12-01", "created_at": "2026-11-19T09:00:00Z"},
         {"id": 2, "app": "hinge", "external_id": "h1", "name": "Bea", "stage": "matched",
          "stage_changed_at": "2026-11-20T10:00:00Z", "notes": "", "next_action": null,
          "due_date": null, "created_at": "2026-11-19T09:00:00Z"}]
        """)

        let cards = try await server.client().cards()

        #expect(cards == [
            Card(id: 1, app: "tinder", name: "Ada", stage: .numberSwapped, notes: "Climbs", nextAction: "Call", dueDate: day(2026, 12, 1)),
            Card(id: 2, app: "hinge", name: "Bea", stage: .matched, notes: "", nextAction: nil, dueDate: nil),
        ])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/cards")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer secret")
    }

    @Test func boardStagesAreTheServersSevenInPipelineOrder() {
        #expect(Stage.allCases.map(\.rawValue) == [
            "matched", "chatting", "number_swapped", "date_set", "dated", "seeing_them", "archived",
        ])
    }

    @Test func listsACardsMessages() async throws {
        server.respond("""
        [{"id": 7, "card_id": 1, "external_id": null, "sender": "them", "body": "Hi!", "sent_at": "2026-11-20T10:00:00Z"},
         {"id": 8, "card_id": 1, "external_id": null, "sender": "me", "body": "Hey", "sent_at": "2026-11-20T10:05:00Z"}]
        """)

        let messages = try await server.client().messages(cardID: 1)

        #expect(messages == [Message(id: 7, sender: .them, body: "Hi!"), Message(id: 8, sender: .me, body: "Hey")])
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/cards/1/messages")
    }

    @Test func savesStageNotesNextActionAndDueDate() async throws {
        server.respond(cardJSON(stage: "date_set", nextAction: "\"Book table\"", dueDate: "\"2026-12-05\""))
        let edited = Card(id: 1, app: "tinder", name: "Ada", stage: .dateSet, notes: "Climbs", nextAction: "Book table", dueDate: day(2026, 12, 5))

        let saved = try await server.client().update(edited)

        #expect(saved == edited)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PATCH")
        #expect(request.url?.absoluteString == "https://crm.test/cards/1")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        #expect(try sentJSON(request) == [
            "stage": "date_set", "notes": "Climbs", "next_action": "Book table", "due_date": "2026-12-05",
        ] as NSDictionary)
    }

    @Test func clearsNextActionAndDueDateWithExplicitNulls() async throws {
        server.respond(cardJSON(stage: "chatting", nextAction: "null", dueDate: "null"))

        _ = try await server.client().update(
            Card(id: 1, app: "tinder", name: "Ada", stage: .chatting, notes: "Climbs", nextAction: nil, dueDate: nil)
        )

        #expect(try sentJSON(server.requests[0]) == [
            "stage": "chatting", "notes": "Climbs", "next_action": NSNull(), "due_date": NSNull(),
        ] as NSDictionary)
    }

    @Test func asksForADraftOnACard() async throws {
        server.respond(
            #"{"id": 5, "card_id": 1, "kind": "opener", "status": "pending", "original": "is biscuit accepting visitors", "edited": null}"#,
            status: 201
        )

        let draft = try await server.client().writeDraft(cardID: 1)

        #expect(draft == Draft(id: 5, kind: .opener, original: "is biscuit accepting visitors", edited: nil))
        #expect(draft.text == "is biscuit accepting visitors")
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/cards/1/drafts")
    }

    @Test func savesTheUsersEditOfADraft() async throws {
        server.respond(
            #"{"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "both. badly.", "edited": "both, badly"}"#
        )

        let draft = try await server.client().saveEdit(draftID: 5, text: "both, badly")

        #expect(draft == Draft(id: 5, kind: .reply, original: "both. badly.", edited: "both, badly"))
        #expect(draft.text == "both, badly")
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PATCH")
        #expect(request.url?.absoluteString == "https://crm.test/drafts/5")
        #expect(try sentJSON(request) == ["edited": "both, badly"] as NSDictionary)
    }

    @Test func savesTheDateRatingAndNote() async throws {
        server.respond("""
        {"id": 1, "app": "tinder", "name": "Ada", "stage": "dated", "notes": "Climbs", "next_action": null,
         "due_date": null, "date_rating": 4, "date_note": "Easy to talk to", "good_date": true}
        """)
        var rated = Card(id: 1, app: "tinder", name: "Ada", stage: .dated, notes: "Climbs")
        rated.dateRating = 4
        rated.dateNote = "Easy to talk to"

        let saved = try await server.client().update(rated)

        #expect(saved == rated)
        #expect(try sentJSON(server.requests[0]) == [
            "stage": "dated", "notes": "Climbs", "next_action": NSNull(), "due_date": NSNull(),
            "date_rating": 4, "date_note": "Easy to talk to",
        ] as NSDictionary)
    }

    @Test func aCardAsksForARatingOnlyWhenItIsDatedAndUnrated() {
        var card = Card(id: 1, app: "tinder", name: "Ada", stage: .dateSet, notes: "")
        #expect(!card.needsDateRating)

        card.stage = .dated
        #expect(card.needsDateRating)

        card.dateRating = 2
        #expect(!card.needsDateRating)
    }

    @Test func reportsTheStatusWhenTheServerRefuses() async {
        server.respond(#"{"detail": "invalid token"}"#, status: 401)

        await #expect(throws: APIError(status: 401)) {
            try await server.client().cards()
        }
    }

    private func cardJSON(stage: String, nextAction: String, dueDate: String) -> String {
        """
        {"id": 1, "app": "tinder", "external_id": null, "name": "Ada", "stage": "\(stage)",
         "stage_changed_at": "2026-11-20T10:00:00Z", "notes": "Climbs", "next_action": \(nextAction),
         "due_date": \(dueDate), "created_at": "2026-11-19T09:00:00Z"}
        """
    }

    private func sentJSON(_ request: URLRequest) throws -> NSDictionary {
        let body = try #require(request.httpBody)
        return try #require(JSONSerialization.jsonObject(with: body) as? NSDictionary)
    }
}
