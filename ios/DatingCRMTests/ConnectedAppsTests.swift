import Foundation
import Testing
@testable import DatingCRM

struct ConnectedAppsTests {
    let server = StubServer()

    @Test func readsEachDatingAppsConnectorStateWithTheAlertThatBrokeIt() async throws {
        server.respond(#"""
        [
          {"app": "tinder", "state": "broken", "alert": {"id": 4, "app": "tinder", "capability": "read_matches",
           "reason": "auth failure", "error": "HTTPStatusError 401", "created_at": "2026-11-24T09:30:00.123456Z"}},
          {"app": "hinge", "state": "no_connector", "alert": null},
          {"app": "bumble", "state": "copilot_only", "alert": null}
        ]
        """#)

        let apps = try await server.client().connectedApps()

        #expect(apps.map(\.app) == ["tinder", "hinge", "bumble"])
        #expect(apps.map(\.state) == [.broken, .noConnector, .copilotOnly])
        #expect(apps[0].alert?.reason == "auth failure")
        #expect(apps[0].alert?.createdAt.timeIntervalSince1970.rounded(.down) == 1_795_512_600)
        #expect(apps[1].alert == nil)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/connectors")
    }

    @Test func readsTheConnectedAndNotConnectedStates() async throws {
        server.respond(#"[{"app": "tinder", "state": "connected", "alert": null}, {"app": "tinder", "state": "not_connected", "alert": null}]"#)

        let apps = try await server.client().connectedApps()

        #expect(apps.map(\.state) == [.connected, .notConnected])
    }

    @Test func connectsAnAppWithThePastedSessionToken() async throws {
        server.respond("", status: 204)

        try await server.client().connect(app: "tinder", token: "tinder-session-secret")

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/connectors/tinder/token")
        #expect(String(data: try #require(request.httpBody), encoding: .utf8) == #"{"token":"tinder-session-secret"}"#)
    }

    @Test func marksAnAppCopilotOnly() async throws {
        server.respond("", status: 204)

        try await server.client().chooseCopilotOnly(app: "tinder")

        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/connectors/tinder/copilot-only")
        #expect(request.httpBody == nil)
    }
}
