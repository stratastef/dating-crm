import SwiftUI

/// A short note on Liquid Glass after an action, with Undo when the action can be taken back.
struct Toast: Identifiable {
    let id = UUID()
    var text: String
    var undo: (() -> Void)?
    /// Set for a Send: a ring counts down the 5 seconds Undo is on offer, then the toast reads this.
    var afterwards: String?
}

extension Toast {
    /// The user's Send, which the server holds 5 seconds for Undo (`UNDO_WINDOW` in `app/send.py`): "Sending…"
    /// with Undo and a draining ring, then "Sent to <name>". `undo` should call `APIClient.undoSend(draftID:)`.
    static func sending(to name: String, undo: @escaping () -> Void) -> Toast {
        Toast(text: "Sending to \(name)…", undo: undo, afterwards: "Sent to \(name)")
    }
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
    @State private var undone = 0

    func body(content: Content) -> some View {
        content
            .overlay(alignment: .bottom) {
                if let current = toast {
                    HStack(spacing: 12) {
                        if current.afterwards != nil {
                            Countdown().id(current.id)  // a new Send restarts the ring
                        }
                        Text(current.text).font(.subheadline)
                        Spacer(minLength: 0)
                        if let undo = current.undo {
                            Button("Undo") {
                                undone += 1
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
                        toast = current.afterwards.map { Toast(text: $0) }
                    }
                }
            }
            .animation(motionReduced ? .easeInOut(duration: 0.2) : .spring(duration: 0.45, bounce: 0.2), value: toast?.id)
            // On the content, which stays: Undo hides the toast at once.
            .sensoryFeedback(.tap, trigger: undone)
    }
}

/// The 5 seconds Undo is on offer: a ring that drains, or with motion reduced a ring that fades.
private struct Countdown: View {
    @Environment(\.motionReduced) private var motionReduced
    @State private var left = 1.0

    var body: some View {
        Ring(left: motionReduced ? 1 : left)
            .opacity(motionReduced ? left : 1)
            .onAppear {
                withAnimation(.linear(duration: 5)) { left = 0 }
            }
    }
}
