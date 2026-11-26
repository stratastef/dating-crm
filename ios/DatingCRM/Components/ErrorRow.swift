import SwiftUI

/// A failed load or save, shown next to what failed: plain words that say what to do, and a tap to try again.
/// Borderless, so it can share a list row with a text field without taking the field's taps.
struct ErrorRow: View {
    let text: String
    let retry: () async -> Void

    var body: some View {
        Button {
            Task { await retry() }
        } label: {
            Label {
                Text(text).foregroundStyle(Color.primary).multilineTextAlignment(.leading)
            } icon: {
                Image(systemName: "exclamationmark.circle.fill").foregroundStyle(.red)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(.rect)
        }
        .buttonStyle(.borderless)
        .accessibilityHint("Tries again")
    }
}
