import Foundation
import Testing
@testable import DatingCRM

/// Notifications, Privacy and the Activity log under You.
struct PrivacyTests {
    let server = StubServer()

    private func body(_ index: Int = 0) throws -> NSDictionary? {
        try server.requests[index].httpBody.map { try JSONSerialization.jsonObject(with: $0) as? NSDictionary } ?? nil
    }

    static let settings = #"""
    {"stalled_after_days": 3, "time_zone": "UTC", "setup_dismissed": false,
     "push_name_previews": false, "blur_photos": true}
    """#

    @Test func readsPushNamePreviewsAndBlurPhotosFromTheSettings() async throws {
        server.respond(Self.settings)

        let settings = try await server.client().settings()

        #expect(settings == UserSettings(pushNamePreviews: false, blurPhotos: true))
        #expect(server.requests[0].httpMethod == "GET")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/settings")
    }

    @Test func setsPushNamePreviewsAlone() async throws {
        server.respond(Self.settings.replacingOccurrences(of: #""push_name_previews": false"#, with: #""push_name_previews": true"#))

        let settings = try await server.client().setPushNamePreviews(true)

        #expect(settings.pushNamePreviews)
        #expect(server.requests[0].httpMethod == "PATCH")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/settings")
        #expect(try body() == ["push_name_previews": true])
    }

    @Test func setsBlurPhotosAlone() async throws {
        server.respond(Self.settings)

        let settings = try await server.client().setBlurPhotos(true)

        #expect(settings.blurPhotos)
        #expect(server.requests[0].httpMethod == "PATCH")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/settings")
        #expect(try body() == ["blur_photos": true])
    }

    // Activity log.

    @Test func readsTheActivityLogWithFullTimestampsAndOptionalNames() async throws {
        server.respond(#"""
        [{"id": 9, "type": "message", "app": "tinder", "target": "card:7", "name": "Ada",
          "trigger": "chat autopilot (autopilot): reply to message 42", "created_at": "2026-11-25T18:04:05.123456Z"},
         {"id": 8, "type": "profile_change", "app": "hinge", "target": "bio", "name": null,
          "trigger": "copilot: user accepted a bio", "created_at": "2026-11-24T09:00:00+00:00"}]
        """#)

        let log = try await server.client().activityLog()

        #expect(log.map(\.id) == [9, 8])
        #expect(log[0].name == "Ada")
        #expect(log[1].name == nil)
        #expect(log[0].trigger == "chat autopilot (autopilot): reply to message 42")
        #expect(abs(log[0].createdAt.timeIntervalSince1970 - 1_795_629_845.123) < 0.001)
        #expect(log[1].createdAt == Date(timeIntervalSince1970: 1_795_510_800))
        #expect(server.requests[0].httpMethod == "GET")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/audit-log")
    }

    private func entry(_ type: String, _ target: String, name: String? = "Ada") -> ActivityEntry {
        ActivityEntry(id: 1, type: type, app: "tinder", target: target, trigger: "", createdAt: .now, name: name)
    }

    @Test func eachActionIsSaidInWordsWithThePersonsName() {
        #expect(entry("message", "card:7").summary == "Sent Ada a message")
        #expect(entry("like", "candidate:3").summary == "Liked Ada")
        #expect(entry("pass", "candidate:3").summary == "Passed on Ada")
        #expect(entry("super_like", "candidate:3").summary == "Sent Ada a Super Like")
        #expect(entry("rose", "candidate:3").summary == "Sent Ada a Rose")
        #expect(entry("boost", "account", name: nil).summary == "Boosted your profile")
        #expect(entry("profile_change", "bio", name: nil).summary == "Changed your bio")
        #expect(entry("profile_change", "photo:4", name: nil).summary == "Changed a photo")
        #expect(entry("calendar_hold", "card:7 hold 2026-12-01T19:00:00+00:00").summary == "Held a time for Ada")
        #expect(entry("calendar_hold", "card:7 release 2026-12-01T19:00:00+00:00").summary == "Released a time held for Ada")
        #expect(entry("calendar_hold", "card:7 confirm 2026-12-01T19:00:00+00:00").summary == "Confirmed the date with Ada")
        // The purged person's card is gone, so the entry has no name.
        #expect(entry("purge", "card:7", name: nil).summary == "Deleted someone's data, as they asked")
        #expect(entry("message", "match:42", name: nil).summary == "Sent someone a message")
    }
}
