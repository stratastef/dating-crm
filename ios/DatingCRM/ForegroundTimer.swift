import Foundation

/// Measures each stretch the app is in the foreground, so the app can report it to the server.
struct ForegroundTimer {
    private var activeSince: Date?

    /// Call on every scene phase change. Returns the whole seconds to report when a foreground stretch ends.
    mutating func phaseChanged(active: Bool, now: Date) -> Int? {
        if active {
            activeSince = activeSince ?? now
            return nil
        }
        guard let start = activeSince else { return nil }
        activeSince = nil
        // The server accepts 1 second to 1 day per report.
        let seconds = min(Int(now.timeIntervalSince(start)), 86400)
        return seconds >= 1 ? seconds : nil
    }
}
