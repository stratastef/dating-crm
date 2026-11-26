import Foundation
import Testing
@testable import DatingCRM

/// Send timing: autopilot's planned send on a card, its words on a Pipeline row, and the night window setting.
struct SendTimingTests {
    let server = StubServer()

    private func body(_ index: Int = 0) throws -> NSDictionary? {
        try server.requests[index].httpBody.map { try JSONSerialization.jsonObject(with: $0) as? NSDictionary } ?? nil
    }

    // The planned send.

    @Test func decodesACardsPlannedSendWithItsFullSendTimeAndReason() async throws {
        server.respond(#"""
        {"id": 1, "app": "tinder", "name": "Ada", "stage": "chatting", "notes": "", "stalled": false, "hot": false,
         "pipeline_group": "handled_by_autopilot", "autopilot_activity": "planned",
         "planned_send": {"id": 5, "card_id": 1, "kind": "reply", "status": "approved", "original": "both. badly.",
                          "edited": null, "guardrail": [], "hot_lead": false, "sendable": true,
                          "send_at": "2026-11-25T19:15:30.123456Z", "timing_reason": "they take their time"}}
        """#)

        let card = try await server.client().card(id: 1)

        let planned = try #require(card.plannedSend)
        #expect(planned.text == "both. badly.")
        #expect(abs(try #require(planned.sendAt).timeIntervalSince1970 - 1_795_634_130.123) < 0.001)
        #expect(planned.timingReason == "they take their time")
        #expect(server.requests[0].httpMethod == "GET")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/cards/1")
    }

    @Test func aCardWithoutAPlannedSendAndADraftFromAnOlderServerDecode() async throws {
        server.respond(#"""
        {"id": 1, "app": "tinder", "name": "Ada", "stage": "chatting", "notes": "", "stalled": false, "hot": false,
         "pending_draft": {"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "yes!",
                           "edited": null, "guardrail": [], "hot_lead": false, "sendable": true}}
        """#)

        let card = try await server.client().card(id: 1)

        #expect(card.plannedSend == nil)
        #expect(card.pendingDraft?.sendAt == nil && card.pendingDraft?.timingReason == nil)
    }

    // The Pipeline row.

    /// 24-hour times, as in the spec's "replies around 20:15".
    let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: "en_GB")
        calendar.timeZone = TimeZone(identifier: "Europe/Berlin")!
        return calendar
    }()

    private func at(day: Int, _ hour: Int, _ minute: Int = 0) -> Date {
        calendar.date(from: DateComponents(year: 2026, month: 11, day: day, hour: hour, minute: minute))!
    }

    private func planned(at sendAt: Date, reason: String) -> Card {
        var card = Card(id: 1, app: "tinder", name: "Ada", stage: .chatting, notes: "")
        card.pipelineGroup = "handled_by_autopilot"
        card.autopilotActivity = "planned"
        card.topic = "museums"
        card.plannedSend = Draft(id: 5, kind: .reply, original: "both. badly.", sendAt: sendAt, timingReason: reason)
        return card
    }

    @Test func aPlannedSendRowSaysWhenItGoesOutAndWhy() {
        let now = at(day: 25, 15)

        #expect(planned(at: at(day: 25, 20, 15), reason: "they take their time").pipelineStatus(now: now, calendar: calendar)
            == "replies around 20:15 · they take their time")
        #expect(planned(at: at(day: 26, 7, 5), reason: "night window").pipelineStatus(now: now, calendar: calendar)
            == "replies tomorrow around 07:05 · night window")
        // No reason from the model: the row ends with the topic, like other autopilot rows.
        #expect(planned(at: at(day: 25, 20, 15), reason: "").pipelineStatus(now: now, calendar: calendar)
            == "replies around 20:15 · talking museums")
    }

    @Test func aRowWithTheUsersScheduledSendSaysWhenItGoesOut() {
        var card = Card(id: 1, app: "tinder", name: "Ada", stage: .chatting, notes: "")
        card.pipelineGroup = "waiting_for_them"
        card.scheduledSend = Draft(id: 5, kind: .reply, original: "both. badly.", sendAt: at(day: 26, 7, 5))

        #expect(card.pipelineStatus(now: at(day: 25, 22), calendar: calendar) == "Your reply goes out tomorrow at 07:05")
    }

    // The night window.

    static let settings = #"""
    {"stalled_after_days": 3, "time_zone": "Europe/Berlin", "setup_dismissed": false,
     "push_name_previews": false, "blur_photos": false, "night_window_start": 22, "night_window_end": 9}
    """#

    @Test func readsTheNightWindowFromTheSettings() async throws {
        server.respond(Self.settings)

        let settings = try await server.client().settings()

        #expect((settings.nightWindowStart, settings.nightWindowEnd) == (22, 9))
    }

    @Test func setsTheNightWindowAlone() async throws {
        server.respond(Self.settings)

        let settings = try await server.client().setNightWindow(start: 22, end: 9)

        #expect((settings.nightWindowStart, settings.nightWindowEnd) == (22, 9))
        #expect(server.requests[0].httpMethod == "PATCH")
        #expect(server.requests[0].url?.absoluteString == "https://crm.test/settings")
        #expect(try body() == ["night_window_start": 22, "night_window_end": 9])
    }
}
