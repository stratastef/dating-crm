import Foundation
import Testing
@testable import DatingCRM

struct SignInTests {
    let server = StubServer()

    private func body(_ request: URLRequest) throws -> NSDictionary? {
        try JSONSerialization.jsonObject(with: try #require(request.httpBody)) as? NSDictionary
    }

    @Test func asksForASignInCodeWithoutAToken() async throws {
        server.respond("", status: 204)

        try await APIClient(baseURL: URL(string: "https://crm.test")!, token: "", transport: server.transport)
            .requestSignInCode(phone: "+15555550100")

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/sign-in/code")
        #expect(try body(request) == ["phone": "+15555550100"])
        #expect(request.value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test func sendsTheInviteCodeWithTheCodeRequestOfANewAccount() async throws {
        server.respond("", status: 204)

        try await APIClient(baseURL: URL(string: "https://crm.test")!, token: "", transport: server.transport)
            .requestSignInCode(phone: "+15555550100", inviteCode: "K7QX-M2PA")

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/sign-in/code")
        #expect(try body(request) == ["phone": "+15555550100", "invite_code": "K7QX-M2PA"])
    }

    @Test func tradesThePhoneNumberAndCodeForATokenAndLearnsWhetherItCreatedTheAccount() async throws {
        server.respond(#"{"token": "device-token", "new_account": true}"#)

        let signedIn = try await APIClient(baseURL: URL(string: "https://crm.test")!, token: "", transport: server.transport)
            .signIn(phone: "+15555550100", code: "123456")

        #expect(signedIn.token == "device-token")
        #expect(signedIn.newAccount)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/sign-in")
        #expect(try body(request) == ["phone": "+15555550100", "code": "123456"])
    }

    @Test func signsOutThisDevice() async throws {
        server.respond("", status: 204)

        try await server.client().signOut()

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/sign-out")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer secret")
    }

    @Test func writesATypedPhoneNumberTheWayTheServerWantsIt() {
        #expect(Session.e164("+1 (415) 555-0100") == "+14155550100")
        #expect(Session.e164(" 0049 170 1234567 ") == "+491701234567")
        #expect(Session.e164("415 555 0100") == nil)  // no country code
        #expect(Session.e164("+1 555") == nil)  // too short
        #expect(Session.e164("+0 415 555 0100") == nil)  // no country code starts with 0
    }
}
