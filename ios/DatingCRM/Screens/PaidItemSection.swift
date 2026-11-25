import SwiftUI

/// A paid item the server proposes to spend, in the review queue. Nothing is spent until the user approves.
struct PaidItemSection: View {
    let client: APIClient
    let item: PaidItem
    /// Called when the item no longer waits: approved or declined.
    let done: () -> Void

    @State private var busy = false
    @State private var error: String?

    var body: some View {
        Section(item.name) {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            Label(item.title, systemImage: "star.circle")
            if !item.reason.isEmpty {
                Text(item.reason).foregroundStyle(.secondary)
            }
            HStack {
                Button("Approve", systemImage: "checkmark") { answer(approve: true) }
                Spacer()
                Button("Decline", systemImage: "xmark", role: .destructive) { answer(approve: false) }
            }
            // Without this, a tap anywhere in the row triggers both buttons.
            .buttonStyle(.borderless)
            .disabled(busy)
        }
    }

    private func answer(approve: Bool) {
        busy = true
        Task {
            defer { busy = false }
            do {
                if approve {
                    if try await client.approve(paidItemID: item.id).status != "spent" {
                        // It no longer waits on the server, so only the message stays until the next refresh.
                        error = "Not spent: the app was not reached or the account has none left."
                        return
                    }
                } else {
                    try await client.decline(paidItemID: item.id)
                }
                done()
            } catch {
                self.error = error.localizedDescription
            }
        }
    }
}
