import Foundation
import Testing
@testable import DatingCRM

/// The Pipeline row's status line: one source per group, worded from the server's codes.
struct PipelineTests {
    let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: "en_US")
        calendar.timeZone = TimeZone(identifier: "Europe/Berlin")!
        return calendar
    }()

    /// Wednesday 25 November 2026, 15:00 in Berlin.
    var now: Date { calendar.date(from: DateComponents(year: 2026, month: 11, day: 25, hour: 15))! }

    func card(_ group: String, reason: String? = nil, activity: String? = nil) -> Card {
        var card = Card(id: 1, app: "tinder", name: "Ada", stage: .chatting, notes: "")
        card.pipelineGroup = group
        card.reason = reason
        card.autopilotActivity = activity
        return card
    }

    func status(_ card: Card) -> String? {
        card.pipelineStatus(now: now, calendar: calendar)
    }

    @Test func waitingForYouSaysTheReason() {
        var handover = card("waiting_for_you", reason: "handover")
        handover.handoverTrigger = "logistics"
        var overdue = card("waiting_for_you", reason: "overdue")
        overdue.nextAction = "Book the bar"

        #expect(status(handover) == "Handover · date plans")
        #expect(status(card("waiting_for_you", reason: "draft_in_review")) == "Reply ready in Review")
        #expect(status(overdue) == "Book the bar")
        #expect(status(card("waiting_for_you", reason: "your_turn")) == "Your turn")
        #expect(status(card("waiting_for_you", reason: "opener_due")) == "Send an opener")
        #expect(status(card("waiting_for_you", reason: "a_reason_from_a_newer_server")) == nil)
    }

    @Test func autopilotAndTheUserSayWhenTheyLastWrote() {
        var sent = card("handled_by_autopilot", activity: "sent_waiting")
        sent.lastMessage = LastMessage(sender: .me, body: "hey", sentAt: now.addingTimeInterval(-4 * 86400))
        var waiting = card("waiting_for_them")
        waiting.lastMessage = LastMessage(sender: .me, body: "hey", sentAt: now.addingTimeInterval(-30))

        #expect(status(sent) == "sent 4d ago, no reply yet")
        #expect(status(card("handled_by_autopilot", activity: "drafting_reply")) == "drafting a reply")
        #expect(status(waiting) == "You wrote just now")
    }

    @Test func offAppSaysTheNextActionAndItsDayOrTheRating() {
        var booking = card("texting_off_app")
        booking.nextAction = "Confirm the booking"
        booking.dueDate = calendar.date(from: DateComponents(year: 2026, month: 11, day: 27))
        var rated = card("texting_off_app")
        rated.dateRating = 5

        #expect(status(booking) == "Confirm the booking · Fri")
        #expect(status(rated) == "Date rated 5/5")
        #expect(status(card("texting_off_app")) == "No next action")
    }
}
