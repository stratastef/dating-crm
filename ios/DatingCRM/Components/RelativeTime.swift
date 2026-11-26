import SwiftUI

/// Relative times for rows: "10m", "4d", "Today", "2 days late". Dates show the year only when it is not this year.
enum RelativeTime {
    /// How long ago, for a row's time: "now", "10m", "3h", "4d", then the date.
    static func since(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        let seconds = Int(now.timeIntervalSince(date))
        return switch seconds {
        case ..<60: "now"
        case ..<3600: "\(seconds / 60)m"
        case ..<86400: "\(seconds / 3600)h"
        case ..<(7 * 86400): "\(seconds / 86400)d"
        default: monthDay(date, now: now, calendar: calendar)
        }
    }

    /// How long ago, in a sentence: "just now", "3h ago", "4d ago", then "on Nov 5".
    static func ago(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        let short = since(date, now: now, calendar: calendar)
        return short == "now" ? "just now" : now.timeIntervalSince(date) < 7 * 86400 ? "\(short) ago" : "on \(short)"
    }

    /// A due day: "Today", "Tomorrow", "Sat" within the week, then the date. Past days are "1 day late", "2 days late".
    static func due(_ day: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        let days = daysFrom(now, to: day, calendar: calendar)
        return days < 0 ? "\(-days) \(-days == 1 ? "day" : "days") late" : self.day(day, now: now, calendar: calendar)
    }

    /// A day: "Today", "Yesterday", "Tomorrow", the weekday within a week either way, then the date.
    static func day(_ day: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        switch daysFrom(now, to: day, calendar: calendar) {
        case 0: "Today"
        case -1: "Yesterday"
        case 1: "Tomorrow"
        case -6...6: day.formatted(style(calendar).weekday(.abbreviated))
        default: monthDay(day, now: now, calendar: calendar)
        }
    }

    /// When a planned send goes out: "around 20:15" today, "tomorrow around 07:05", else its day too.
    static func around(_ date: Date, now: Date = .now, calendar: Calendar = .current) -> String {
        let time = date.formatted(style(calendar).hour().minute())
        return switch daysFrom(now, to: date, calendar: calendar) {
        case 0: "around \(time)"
        case 1: "tomorrow around \(time)"
        default: "\(day(date, now: now, calendar: calendar)) around \(time)"
        }
    }

    /// Calendar days from `now`'s day to `day`'s day: negative in the past.
    static func daysFrom(_ now: Date, to day: Date, calendar: Calendar = .current) -> Int {
        calendar.dateComponents([.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: day)).day ?? 0
    }

    private static func monthDay(_ date: Date, now: Date, calendar: Calendar) -> String {
        let format = style(calendar).month(.abbreviated).day()
        let sameYear = calendar.isDate(date, equalTo: now, toGranularity: .year)
        return date.formatted(sameYear ? format : format.year())
    }

    private static func style(_ calendar: Calendar) -> Date.FormatStyle {
        Date.FormatStyle(locale: calendar.locale ?? .current, calendar: calendar, timeZone: calendar.timeZone)
    }
}

/// A row's time since `date` ("10m"), which VoiceOver reads in words ("10 minutes ago").
struct TimeAgoText: View {
    let date: Date

    var body: some View {
        Text(RelativeTime.since(date))
            .accessibilityLabel(date.formatted(.relative(presentation: .named)))
    }
}
