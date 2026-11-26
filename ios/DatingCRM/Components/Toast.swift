import SwiftUI

/// A short note on Liquid Glass after an action, with Undo when the action can be taken back.
struct Toast: Identifiable {
    let id = UUID()
    var text: String
    var undo: (() -> Void)?
}

extension View {
    /// Shows `toast` at the bottom for 5 seconds, then sets it to nil. Undo runs the action and hides it at once.
    func toast(_ toast: Binding<Toast?>) -> some View {
        modifier(ToastPresenter(toast: toast))
    }
}

private struct ToastPresenter: ViewModifier {
    @Binding var toast: Toast?
    @Environment(\.motionReduced) private var motionReduced

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .bottom) {
                if let current = toast {
                    HStack(spacing: 12) {
                        Text(current.text).font(.subheadline)
                        Spacer(minLength: 0)
                        if let undo = current.undo {
                            Button("Undo") {
                                undo()
                                toast = nil
                            }
                            .fontWeight(.semibold)
                            .frame(minWidth: 44, minHeight: 44)
                        }
                    }
                    .padding(.leading, 18)
                    .padding(.trailing, 8)
                    .frame(minHeight: 56)
                    .glassEffect(.regular, in: .capsule)
                    .padding(.horizontal, 14)
                    .padding(.bottom, 8)
                    .transition(motionReduced ? .opacity : .move(edge: .bottom).combined(with: .opacity))
                    .task(id: current.id) {
                        AccessibilityNotification.Announcement(current.text).post()
                        // Cancelled when another toast replaces this one, which then hides itself.
                        guard (try? await Task.sleep(for: .seconds(5))) != nil else { return }
                        toast = nil
                    }
                }
            }
            .animation(motionReduced ? .easeInOut(duration: 0.2) : .spring(duration: 0.45, bounce: 0.2), value: toast?.id)
    }
}
