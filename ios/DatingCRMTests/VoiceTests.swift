import Foundation
import Testing
@testable import DatingCRM

struct VoiceTests {
    let server = StubServer()

    @Test func readsTheServersQuestionsAndTheUsersAnswers() async throws {
        server.respond("""
        {"questions": ["How do you open?", "Emoji or not?"], "answers": {"How do you open?": "A joke"}, "profile": null}
        """)

        let voice = try await server.client().voice()

        #expect(voice == Voice(questions: ["How do you open?", "Emoji or not?"], answers: ["How do you open?": "A joke"]))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/voice")
    }

    @Test func savesTheAnswersKeyedByTheQuestionsExactText() async throws {
        server.respond("""
        {"questions": ["How do you open?"], "answers": {"How do you open?": "A joke", "Use_of CAPS?": "Never"},
         "profile": "Dry."}
        """)
        let answers = ["How do you open?": "A joke", "Use_of CAPS?": "Never"]

        let saved = try await server.client().saveAnswers(answers)

        #expect(saved.answers == answers)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/voice/questionnaire")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["answers": answers] as NSDictionary)
    }
}
