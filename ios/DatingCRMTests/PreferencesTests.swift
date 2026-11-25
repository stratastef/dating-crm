import Foundation
import Testing
@testable import DatingCRM

struct PreferencesTests {
    let server = StubServer()

    @Test func readsThePreferencesInForce() async throws {
        server.respond("""
        {"version": 2, "wishes": "Curious and kind.", "must_haves": ["wants kids"], "dealbreakers": ["smokes"]}
        """)

        let preferences = try await server.client().preferences()

        #expect(preferences == Preferences(wishes: "Curious and kind.", mustHaves: ["wants kids"], dealbreakers: ["smokes"]))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/preferences")
    }

    @Test func savesWishesMustHavesAndDealbreakers() async throws {
        server.respond("""
        {"version": 3, "wishes": "Curious.", "must_haves": ["wants kids", "nearby"], "dealbreakers": []}
        """)
        let edited = Preferences(wishes: "Curious.", mustHaves: ["wants kids", "nearby"], dealbreakers: [])

        let saved = try await server.client().save(edited)

        #expect(saved == edited)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/preferences")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == [
            "wishes": "Curious.", "must_haves": ["wants kids", "nearby"], "dealbreakers": [String](),
        ] as NSDictionary)
    }
}
