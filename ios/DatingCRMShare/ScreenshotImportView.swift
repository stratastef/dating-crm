import SwiftUI

/// The share extension's one screen: progress, then the draft with a Copy button, or what went wrong.
struct ScreenshotImportView: View {
    let model: ScreenshotImport
    let done: () -> Void

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .reading:
                    ProgressView("Reading the screenshot…")
                case .draft(let draft):
                    VStack(alignment: .leading, spacing: 16) {
                        Text(draft.text).textSelection(.enabled)
                        Button("Copy", systemImage: "doc.on.doc") { UIPasteboard.general.string = draft.text }
                            .buttonStyle(.borderedProminent)
                        Spacer()
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding()
                case .failed(let message):
                    ContentUnavailableView("No draft", systemImage: "exclamationmark.triangle", description: Text(message))
                }
            }
            .navigationTitle("Draft")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done", action: done) } }
        }
    }
}
