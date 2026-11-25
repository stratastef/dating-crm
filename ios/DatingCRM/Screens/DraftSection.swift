import SwiftUI
import UIKit

/// The copilot draft on a card: ask Claude for an opener or reply, edit it and copy it into the dating app.
struct DraftSection: View {
    let client: APIClient
    let cardID: Int

    @State private var draft: Draft?
    @State private var text = ""
    @State private var writing = false
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
            error = nil
        } catch let refused as APIError where refused.status == 409 {
            error = "Your style profile is not written yet. Answer the voice questionnaire first."
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func copy() async {
        UIPasteboard.general.string = text
        guard let current = draft, text != current.text else { return }
        do {
            draft = try await client.saveEdit(draftID: current.id, text: text)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
