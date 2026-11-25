import Foundation
import Testing
@testable import DatingCRM

struct ReadTests {
    let server = StubServer()

    @Test func loadsTheReadOfACardWithEvidenceAndConfidence() async throws {
        server.respond("""
        [{"id": 7, "card_id": 1, "kind": "texting_style", "value": "short, lots of emoji",
          "evidence": "'omg yes 😂'", "confidence": 0.85, "corrected": null}]
        """)

        let read = try await server.client().read(cardID: 1)

        #expect(read == [
            Inference(id: 7, kind: "texting_style", value: "short, lots of emoji", evidence: "'omg yes 😂'", confidence: 0.85)
        ])
        #expect(read[0].title == "Texting style")
        #expect(read[0].text == "short, lots of emoji")
        #expect(server.requests.first?.httpMethod == "GET")
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/cards/1/read")
    }

    @Test func asksForANewReadOfACard() async throws {
        server.respond("[]")

        let read = try await server.client().makeRead(cardID: 1)

        #expect(read.isEmpty)
        #expect(server.requests.first?.httpMethod == "POST")
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/cards/1/read")
    }

    @Test func aCorrectionReplacesTheInferredValue() async throws {
        server.respond("""
        {"id": 7, "card_id": 1, "kind": "tone", "value": "bold", "evidence": "teases back", "confidence": 0.6,
         "corrected": "sincere"}
        """)

        let corrected = try await server.client().correct(inferenceID: 7, text: "sincere")

        #expect(corrected.value == "bold")
        #expect(corrected.text == "sincere")
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PATCH")
        #expect(request.url?.absoluteString == "https://crm.test/inferences/7")
        let sent = try JSONSerialization.jsonObject(with: try #require(request.httpBody)) as? NSDictionary
        #expect(sent == ["corrected": "sincere"] as NSDictionary)
    }
}
