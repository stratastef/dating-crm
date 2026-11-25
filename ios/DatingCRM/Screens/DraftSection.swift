import SwiftUI
import UIKit

/// The copilot draft on a card: ask Claude for an opener or reply, edit it, then send it or copy it into the dating app.
struct DraftSection: View {
    let client: APIClient
    let cardID: Int

    @State private var draft: Draft?
    @State private var text = ""
    @State private var writing = false
    @State private var sending = false
    @State private var sent = false
    @State private var error: String?

    var body: some View {
        Section("Draft") {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            if draft != nil {
                TextField("Draft", text: $text, axis: .vertical)
                    .lineLimit(2...)
                // Copy is the moment the user settles on the wording, so the edit is saved then.
                Button("Copy", systemImage: "doc.on.doc") {
                    Task { await copy() }
                }
                .disabled(text.isEmpty)
                if sent {
                    // The worker sends it; the message shows on the card once it has.
                    Label("Sending", systemImage: "checkmark")
                } else {
                    Button("Send", systemImage: "paperplane") {
                        Task { await send() }
                    }
                    .disabled(text.isEmpty || sending)
                }
            }
            Button(draft == nil ? "Write draft" : "Write another", systemImage: "sparkles") {
                Task { await write() }
            }
            .disabled(writing)
        }
    }

    private func write() async {
        writing = true
        defer { writing = false }
        do {
            let written = try await client.writeDraft(cardID: cardID)
            draft = written
            text = written.text
            sent = false
            error = nil
        } catch let refused as APIError where refused.status == 409 {
            error = "Your style profile is not written yet. Answer the voice questionnaire first."
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func copy() async {
        UIPasteboard.general.string = text
        do {
            try await saveEdit()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func send() async {
        guard let current = draft else { return }
        sending = true
        defer { sending = false }
        do {
            try await saveEdit()
            try await client.sendDraft(draftID: current.id)
            sent = true
            error = nil
        } catch let refused as APIError where refused.status == 409 {
            error = "The server did not send it: the app is paused or sending is off for it. Copy the draft instead."
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func saveEdit() async throws {
        guard let current = draft, text != current.text else { return }
        draft = try await client.saveEdit(draftID: current.id, text: text)
    }
}
