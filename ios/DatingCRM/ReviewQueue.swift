import Foundation

/// The review queue as Review shows it. Dismissing a draft takes it out at once, but the server hears of it only
/// once Undo is no longer on offer: Undo puts it back without a call, and a dismissal never reaches the server
/// half undone.
@Observable final class ReviewQueue {
    private(set) var items: [QueueItem] = []
    private(set) var loaded = false
    var error: String?

    private let client: APIClient
    private let undoWindow: Duration
    /// Drafts dismissed but not yet sent to the server, by item ID, with where they stood.
    private var dismissing: [String: (item: QueueItem, index: Int, commit: Task<Void, Never>)] = [:]

    /// `undoWindow` matches how long the toast offers Undo.
    init(client: APIClient, undoWindow: Duration = .seconds(5)) {
        self.client = client
        self.undoWindow = undoWindow
    }

    func load() async {
        do {
            items = try await client.queue().filter { dismissing[$0.id] == nil }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    /// For an item the server no longer holds: sent, declined, taken over or handed back.
    func remove(_ item: QueueItem) {
        items.removeAll { $0.id == item.id }
    }

    /// Takes a draft out of Review now and dismisses it on the server after `undoWindow`, unless `undo` runs first.
    /// Returns the wait-then-dismiss task.
    @discardableResult
    func dismiss(_ item: QueueItem) -> Task<Void, Never> {
        let index = items.firstIndex { $0.id == item.id } ?? items.count
        remove(item)
        let commit = Task {
            guard (try? await Task.sleep(for: undoWindow)) != nil, let draft = item.draft else { return }
            dismissing[item.id] = nil
            do {
                try await client.dismiss(draftID: draft.id)
            } catch {
                await load()  // it is still pending on the server, so it comes back
                self.error = "The draft for \(item.cardName) was not dismissed: \(error.localizedDescription)"
            }
        }
        dismissing[item.id] = (item, index, commit)
        return commit
    }

    func undo(_ item: QueueItem) {
        guard let dismissed = dismissing.removeValue(forKey: item.id) else { return }
        dismissed.commit.cancel()
        items.insert(dismissed.item, at: min(dismissed.index, items.count))
    }
}
