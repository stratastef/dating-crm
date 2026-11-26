import Foundation
import Testing
@testable import DatingCRM

struct BiosTests {
    let server = StubServer()

    @Test func readsTheBioAcceptedForAnApp() async throws {
        server.respond(#"{"bio": "Climber.", "prompts": {"My_simple Pleasures": "Coffee"}}"#)

        let bio = try await server.client().bio(app: "hinge")

        #expect(bio == Bio(bio: "Climber.", prompts: ["My_simple Pleasures": "Coffee"]))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/bios/hinge")
    }

    @Test func sendsTheBioAndPromptsToRewriteAndReadsTheRewrite() async throws {
        server.respond(#"{"bio": "Climbs things.", "prompts": {"My_simple Pleasures": "Strong coffee"}}"#)
        let current = Bio(bio: "Climber.", prompts: ["My_simple Pleasures": "Coffee"])

        let rewrite = try await server.client().rewriteBio(app: "hinge", current)

        #expect(rewrite == Bio(bio: "Climbs things.", prompts: ["My_simple Pleasures": "Strong coffee"]))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/bios/hinge/rewrite")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary
            == ["bio": "Climber.", "prompts": ["My_simple Pleasures": "Coffee"]] as NSDictionary)
    }

    @Test func acceptsARewriteForAnApp() async throws {
        server.respond(#"{"bio": "Climbs things.", "prompts": {}}"#)

        let accepted = try await server.client().acceptBio(app: "tinder", Bio(bio: "Climbs things."))

        #expect(accepted == Bio(bio: "Climbs things."))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/bios/tinder")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary
            == ["bio": "Climbs things.", "prompts": [:]] as NSDictionary)
    }
}
