import Foundation
import Testing
@testable import DatingCRM

struct CalendarTests {
    let server = StubServer()

    @Test func readsWhetherGoogleCalendarIsConnected() async throws {
        server.respond(#"{"connected": true}"#)

        #expect(try await server.client().calendarConnected())
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/calendar")
    }

    @Test func getsGooglesConsentPage() async throws {
        server.respond(#"{"url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=abc&state=s%2B1"}"#)

        let url = try await server.client().calendarConsentURL()

        #expect(url.absoluteString == "https://accounts.google.com/o/oauth2/v2/auth?client_id=abc&state=s%2B1")
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "GET")
        #expect(request.url?.absoluteString == "https://crm.test/calendar/connect")
    }
}
