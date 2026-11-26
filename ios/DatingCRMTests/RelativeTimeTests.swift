import Foundation
import Testing
@testable import DatingCRM

struct RelativeTimeTests {
    let calendar: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.locale = Locale(identifier: "en_US")
        calendar.timeZone = TimeZone(identifier: "Europe/Berlin")!
        return calendar
    }()

    /// Wednesday 25 November 2026, 15:00 in Berlin.
    var now: Date { at(2026, 11, 25, 15) }

    func at(_ year: Int, _ month: Int, _ day: Int, _ hour: Int = 0, _ minute: Int = 0) -> Date {
        calendar.date(from: DateComponents(year: year, month: month, day: day, hour: hour, minute: minute))!
    }

    @Test func rowTimesAreShortAndDropTheYearOnlyWithinThisYear() {
        let since = { RelativeTime.since($0, now: now, calendar: calendar) }
        #expect(since(now.addingTimeInterval(-30)) == "now")
        #expect(since(now.addingTimeInterval(-10 * 60)) == "10m")
        #expect(since(now.addingTimeInterval(-3 * 3600)) == "3h")
        #expect(since(now.addingTimeInterval(-4 * 86400)) == "4d")
        #expect(since(at(2026, 11, 5, 9)) == "Nov 5")
        #expect(since(at(2025, 12, 20, 9)) == "Dec 20, 2025")
    }

    @Test func dueDaysSayHowManyDaysLateWithPlurals() {
        let due = { RelativeTime.due($0, now: now, calendar: calendar) }
        #expect(due(at(2026, 11, 25)) == "Today")
        #expect(due(at(2026, 11, 24)) == "1 day late")
        #expect(due(at(2026, 11, 23)) == "2 days late")
        #expect(due(at(2026, 11, 26)) == "Tomorrow")
        #expect(due(at(2026, 11, 28)) == "Sat")
        #expect(due(at(2026, 12, 24)) == "Dec 24")
        #expect(due(at(2027, 1, 15)) == "Jan 15, 2027")
    }

    @Test func pastDaysNameTheWeekdayWithinAWeek() {
        let day = { RelativeTime.day($0, now: now, calendar: calendar) }
        #expect(day(at(2026, 11, 24, 21)) == "Yesterday")
        #expect(day(at(2026, 11, 22, 19)) == "Sun")
        #expect(day(at(2026, 11, 10)) == "Nov 10")
    }
}
