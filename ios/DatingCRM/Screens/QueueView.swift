import SwiftUI

/// The review queue: pending drafts to approve, edit or dismiss, and handovers to take over. Hot leads come first.
struct QueueView: View {
    let client: APIClient

    @State private var items: [QueueItem] = []
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            if loaded && items.isEmpty {
                ContentUnavailableView("Nothing to review", systemImage: "checkmark.circle")
            }
            ForEach(items) { item in
                // Kinds this version does not know have no draft and are not shown.
                if let draft = item.draft {
                    DraftRow(item: item, draft: draft) { text, approve in
                        await decide(item, draft: draft, text: text, approve: approve)
                    }
                } else if let paidItem = item.paidItem {
                    PaidItemSection(client: client, item: paidItem) { items.removeAll { $0.id == item.id } }
                } else if item.kind == "handover", let cardID = item.cardID {
                    HandoverSection(
                        client: client, cardID: cardID, title: item.cardName, suggestions: item.suggestions ?? [],
                        // Taken over, the chat no longer waits in the queue.
                        state: Binding(get: { .pending }, set: { _ in items.removeAll { $0.id == item.id } })
                    )
                }
            }
        }
        .navigationTitle("Review")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            items = try await client.queue()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        loaded = true
    }

    private func decide(_ item: QueueItem, draft: Draft, text: String, approve: Bool) async {
        do {
            if approve {
                if text != draft.text {
                    _ = try await client.saveEdit(draftID: draft.id, text: text)
                }
                try await client.approve(draftID: draft.id)
            } else {
                try await client.dismiss(draftID: draft.id)
            }
            items.removeAll { $0.id == item.id }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct DraftRow: View {
    let item: QueueItem
    /// Called with the text as edited and whether the user approved (true) or dismissed (false).
    let decide: (String, Bool) async -> Void

    @State private var text: String
    @State private var busy = false

    init(item: QueueItem, draft: Draft, decide: @escaping (String, Bool) async -> Void) {
        self.item = item
        self.decide = decide
        _text = State(initialValue: draft.text)
    }

    var body: some View {
        Section {
            TextField("Draft", text: $text, axis: .vertical)
                .lineLimit(2...)
            HStack {
                Button("Approve", systemImage: "checkmark") { run(approve: true) }
                    .disabled(text.isEmpty)
                Spacer()
                Button("Dismiss", systemImage: "xmark", role: .destructive) { run(approve: false) }
            }
            // Without this, a tap anywhere in the row triggers both buttons.
            .buttonStyle(.borderless)
            .disabled(busy)
        } header: {
            HStack {
                Text(item.cardName)
                if item.hot {
                    Label("Hot lead", systemImage: "flame.fill").foregroundStyle(.orange)
                }
            }
        }
    }

    private func run(approve: Bool) {
        busy = true
        Task {
            await decide(text, approve)
            busy = false
        }
    }
}
