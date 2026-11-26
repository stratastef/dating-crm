import SwiftUI

/// A text field that grows to fit what is typed and hides the keyboard on return. The whole 44 pt row takes the tap.
/// `label` is what VoiceOver reads; `prompt` shows while the field is empty.
struct GrowingField: View {
    let label: String
    let prompt: String
    @Binding var text: String
    @FocusState private var focused: Bool

    var body: some View {
        TextField(
            label,
            text: Binding(
                get: { text },
                set: { typed in
                    // A vertical field types a newline on return instead of submitting: take it as Done.
                    // Pasted lines are joined with a space.
                    if typed.contains("\n") {
                        focused = false
                        text = typed.split(separator: "\n").joined(separator: " ")
                    } else {
                        text = typed
                    }
                }),
            prompt: Text(prompt).foregroundStyle(.secondaryText),
            axis: .vertical
        )
        .submitLabel(.done)
        .focused($focused)
        .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
        .contentShape(.rect)
        .onTapGesture { focused = true }
    }
}
