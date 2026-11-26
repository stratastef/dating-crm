import Foundation

/// An action that waits before it runs, so a toast's Undo can take it back first. For what the server cannot take
/// back once done, such as a swipe sent to the dating app.
@MainActor
final class Held {
    private var task: Task<Void, Never>?
    private var started = false

    /// Runs `action` after `delay`, the toast's 5 seconds by default, unless `undo()` comes first. The wait goes on
    /// when the screen goes away or nothing keeps this object.
    init(after delay: Duration = .seconds(5), _ action: @escaping @MainActor () async -> Void) {
        task = Task { [weak self] in
            // `isCancelled` too: an undo can land after the sleep ended and before this resumes.
            guard (try? await Task.sleep(for: delay)) != nil, !Task.isCancelled else { return }
            self?.started = true
            await action()
        }
    }

    /// Takes the action back. False when it already started: too late to undo.
    func undo() -> Bool {
        guard !started else { return false }
        task?.cancel()
        return true
    }
}
