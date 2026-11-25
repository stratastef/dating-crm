import Foundation
import Testing
@testable import DatingCRM

struct SessionTests {
    let server = StubServer()
    // A fresh Keychain service and defaults suite per test, so tests never see each other's session.
    let name = "DatingCRMTests.\(UUID().uuidString)"

    private func session() -> Session {
        Session(keychainService: name, defaults: UserDefaults(suiteName: name)!, transport: server.transport)
    }

    @Test func startsSignedOut() {
        #expect(session().client == nil)
    }

    @Test func signsInAgainstTheServerAndKeepsTheSessionAcrossLaunches() async throws {
        server.respond("[]")
        let session = session()

        try await session.signIn(serverURL: " https://crm.test ", token: " secret\n")

        #expect(session.client?.baseURL.absoluteString == "https://crm.test")
        #expect(session.client?.token == "secret")
        #expect(server.requests.first?.value(forHTTPHeaderField: "Authorization") == "Bearer secret")

        let relaunched = self.session()
        #expect(relaunched.client?.baseURL.absoluteString == "https://crm.test")
        #expect(relaunched.client?.token == "secret")
        // The token lives in the Keychain only.
        #expect(!UserDefaults(suiteName: name)!.dictionaryRepresentation().values.contains { $0 as? String == "secret" })

        relaunched.signOut()
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

    @Test func signingOutForgetsTheSession() async throws {
        server.respond("[]")
        let session = session()
        try await session.signIn(serverURL: "https://crm.test", token: "secret")

        session.signOut()

        #expect(session.client == nil)
        #expect(self.session().client == nil)
    }
}
