import Foundation
import Testing
@testable import DatingCRM

struct SessionTests {
    let server = StubServer()
    // A fresh Keychain service and defaults suite per test, so tests never see each other's session.
    let name = "DatingCRMTests.\(UUID().uuidString)"

    private func session() -> Session {
        Session(
            keychainService: name, defaults: UserDefaults(suiteName: name)!, transport: server.transport,
            serverURL: URL(string: "https://crm.test")!)
    }

    @Test func startsSignedOut() {
        #expect(session().client == nil)
    }

    @Test func signsInWithAPhoneNumberAndSignInCodeAndKeepsTheSessionForTheShareExtension() async throws {
        server.respond("", status: 204)
        server.respond(#"{"token": "device-token"}"#)
        let session = session()

        try await session.requestCode(phone: "+15555550100")
        #expect(session.client == nil)
        try await session.signIn(phone: "+15555550100", code: "123456")

        #expect(server.requests.map { $0.url?.path() } == ["/sign-in/code", "/sign-in"])
        #expect(session.client?.baseURL.absoluteString == "https://crm.test")
        #expect(session.client?.token == "device-token")
        // The share extension makes its own `Session()` and finds the same server and token.
        let shareExtension = self.session()
        #expect(shareExtension.client?.baseURL.absoluteString == "https://crm.test")
        #expect(shareExtension.client?.token == "device-token")

        server.respond("", status: 204)
        await shareExtension.signOut()
    }

    @Test func staysSignedOutWhenTheSignInCodeIsWrong() async {
        server.respond(#"{"detail": "wrong_code"}"#, status: 401)
        let session = session()

        await #expect(throws: APIError(status: 401)) {
            try await session.signIn(phone: "+15555550100", code: "000000")
        }

        #expect(session.client == nil)
        #expect(self.session().client == nil)
    }

    @Test func signsInAgainstTheServerAndKeepsTheSessionAcrossLaunches() async throws {
        server.respond("[]")
        let session = session()

        try await session.signIn(serverURL: " https://dev.test ", token: " secret\n")

        #expect(session.client?.baseURL.absoluteString == "https://dev.test")
        #expect(session.client?.token == "secret")
        #expect(server.requests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer secret")

        let relaunched = self.session()
        #expect(relaunched.client?.baseURL.absoluteString == "https://dev.test")
        #expect(relaunched.client?.token == "secret")
        // The token lives in the Keychain only.
        #expect(!UserDefaults(suiteName: name)!.dictionaryRepresentation().values.contains { $0 as? String == "secret" })

        server.respond("", status: 204)
        await relaunched.signOut()
    }

    @Test func staysSignedOutWhenTheServerRejectsTheToken() async {
        server.respond(#"{"detail": "invalid token"}"#, status: 401)
        let session = session()

        await #expect(throws: APIError(status: 401)) {
            try await session.signIn(serverURL: "https://crm.test", token: "wrong")
        }

        #expect(session.client == nil)
        #expect(self.session().client == nil)
    }

    @Test func refusesAServerURLThatIsNotHTTP() async {
        let session = session()

        await #expect(throws: SignInError.invalidServerURL) {
            try await session.signIn(serverURL: "crm.test", token: "secret")
        }

        #expect(server.requests.isEmpty)
    }

    @Test func signingOutRevokesThisDevicesTokenOnTheServer() async throws {
        server.respond("[]")
        let session = session()
        try await session.signIn(serverURL: "https://crm.test", token: "secret")
        server.respond("", status: 204)

        await session.signOut()

        let request = try #require(server.requests.last)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/sign-out")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer secret")
        #expect(session.client == nil)
        #expect(self.session().client == nil)
    }

    @Test func signingOutForgetsTheSessionEvenWhenTheServerCannotBeReached() async throws {
        server.respond("[]")
        let session = session()
        try await session.signIn(serverURL: "https://crm.test", token: "secret")
        server.respond("", status: 503)

        await session.signOut()

        #expect(session.client == nil)
        #expect(self.session().client == nil)
    }
}
