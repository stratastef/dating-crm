import SwiftUI
import UIKit

/// The card's draft, docked at the bottom of its chat like a composer, on Liquid Glass (ADR 0003, ADR 0009). It
/// docks autopilot's planned send (`Card.plannedSend`) first: a ring draining until it goes out, its time and
/// reason, its text, Hold and Send now. Then the user's scheduled send (`Card.scheduledSend`): when it goes out,
/// with Cancel. Otherwise it docks the first draft of the card's draft list (`Card.drafts`, newest first) in one
/// of three states:
/// - pending: editable under the AI draft marker, with when it is best sent (ADR 0008), and Send at and Send where
///   the app can send it, Copy where it cannot;
/// - copied: "Copied, not sent yet", with when it is best sent, Clear and Copy again;
/// - failed: why, still editable, with Copy and Retry.
///
/// With none of these it offers Write draft in Matched and Chatting, and shows nothing from Number swapped on. Without
/// a style profile, Write draft sets `needsVoice` and the card opens the voice questionnaire.
struct DraftComposer: View {
    let client: APIClient
    let card: Card
    @Binding var toast: Toast?
    @Binding var needsVoice: Bool
    /// Reloads the card after the server changed its drafts.
    let reload: () async -> Void
    /// After a Send: reloads until the sent message is in the chat.
    let sent: () async -> Void

    @State private var text = ""
    @State private var busy = false
    @State private var error: String?
    /// A cleared draft hides at once; the server hears of it once the toast's Undo is over.
    @State private var clearing: (draftID: Int, held: Held)?

    private var draft: Draft? { card.drafts?.first { $0.id != clearing?.draftID } }

    private var datingApp: String { card.app.capitalized }

    var body: some View {
        if let planned = card.plannedSend {  // it answers already: no second reply
            plannedDock(planned)
        } else if let scheduled = card.scheduledSend {
            scheduledDock(scheduled)
        } else if let draft {
            dock(draft)
                .onChange(of: draft.id, initial: true) { text = draft.text }
        } else if card.stage.chatsInApp {
            box {
                if let error {
                    ErrorRow(text: error) { await write() }
                }
                Button(busy ? "Writing…" : "Write draft") { Task { await write() } }
                    .buttonStyle(.primaryCapsule)
                    .disabled(busy)
            }
        }
    }

    private func dock(_ draft: Draft) -> some View {
        let copied = draft.status == "copied"
        let failed = draft.status == "failed"
        // It denies being AI and the user has not changed it: neither sent nor copied until they do.
        let waitsForEdit = draft.deniesAI && text == draft.text
        let sendAt = failed || waitsForEdit || !draft.sendable ? nil : draft.suggestedSendAt
        return box {
            if copied {
                Text("Copied, not sent yet").font(.headline)
                Inset {
                    Text(draft.text)
                    SuggestedSendTime(draft: draft)  // when to paste it
                }
                if draft.deniesAI {
                    warning("It says you're not an AI. Clear it and write another.")
                }
            } else {
                if failed {
                    // The app's error may have come after the message reached the match.
                    warning("Sending failed. It may still have reached \(datingApp), so check the chat before you send it again.")
                }
                Inset {
                    AIMarker(.draft)
                    TextField("Draft", text: $text, axis: .vertical)
                        .lineLimit(1...6)
                    if !failed {
                        SuggestedSendTime(draft: draft)
                    }
                }
                if waitsForEdit {
                    warning("It says you're not an AI. Edit it before you send it.")
                }
            }
            if let error {
                ErrorRow(text: error) { await reload() }
            }
            AdaptiveStack(spacing: 8) {
                if copied {
                    Button("Clear") { clear(draft) }
                        .buttonStyle(.secondaryCapsule)
                    if !draft.deniesAI {
                        Button("Copy again") {
                            UIPasteboard.general.string = draft.text
                            toast = Toast(text: "Copied. Paste it in \(datingApp).")
                        }
                        .buttonStyle(.primaryCapsule)
                    }
                } else {
                    if failed {
                        Button("Copy") { Task { await act(draft, send: false) } }
                            .buttonStyle(.secondaryCapsule)
                    }
                    if let sendAt {
                        SendAtButton(at: sendAt) { Task { await act(draft, send: true, at: sendAt) } }
                            .disabled(text.isEmpty)
                    }
                    // A failed send the app cannot retry now offers Copy only.
                    if !waitsForEdit, draft.sendable || !failed {
                        Button(failed ? "Retry" : draft.sendable ? "Send" : "Copy") {
                            Task { await act(draft, send: draft.sendable) }
                        }
                        .buttonStyle(.primaryCapsule)
                        .disabled(text.isEmpty)
                    }
                }
            }
            .disabled(busy)
        }
    }

    /// Autopilot's planned send: it goes out alone at its send time unless the user holds it or sends it now.
    private func plannedDock(_ planned: Draft) -> some View {
        let about = VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                PlannedRing(draft: planned)
                Text("Replies \(planned.sendAt.map { RelativeTime.around($0) } ?? "soon")").font(.headline)
            }
            if let reason = planned.timingReason, !reason.isEmpty {
                Text(reason.prefix(1).uppercased() + reason.dropFirst()).font(.subheadline).foregroundStyle(.secondaryText)
            }
            Inset {
                AIMarker(.autopilot)
                Text(planned.text)
            }
        }
        return box {
            // At the largest text sizes it scrolls above the buttons: the text that goes out is never cut.
            ViewThatFits(in: .vertical) {
                about
                ScrollView { about }
            }
            if let error {
                ErrorRow(text: error) { await reload() }
            }
            AdaptiveStack(spacing: 8) {
                Button("Hold") { Task { await hold(planned) } }
                    .buttonStyle(.secondaryCapsule)
                if planned.sendable {  // the app cannot send it now: Hold only, and it goes to Review
                    Button("Send now") { Task { await sendNow(planned) } }
                        .buttonStyle(.primaryCapsule)
                }
            }
            .disabled(busy)
        }
    }

    /// The composer's surface. Glass on the background, not the content: glass would make the black Send capsule
    /// grey. The fill keeps `.primary` text at 4.5:1 over any bubble.
    private func box<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background {
                RoundedRectangle(cornerRadius: 28)
                    .fill(Color(uiColor: .systemBackground).opacity(0.72))
                    .glassEffect(.regular, in: .rect(cornerRadius: 28))
            }
            .padding(.horizontal, 10)
            .padding(.bottom, 6)
    }

    private func warning(_ text: String) -> some View {
        Text("\(Image(systemName: "exclamationmark.triangle")) \(text)")
    }

    private func write() async {
        busy = true
        defer { busy = false }
        do {
            _ = try await client.writeDraft(cardID: card.id)
            error = nil
            await reload()
        } catch let refused as APIError where refused.status == 409 {
            error = nil
            needsVoice = true  // no style profile yet: the questionnaire, not an error
        } catch {
            self.error = "No draft was written. Tap to try again."
        }
    }

    /// The user's scheduled send: when it goes out and its text, with Cancel, which docks it again as pending.
    private func scheduledDock(_ draft: Draft) -> some View {
        box {
            Text(draft.sendAt.map { "Goes out \(RelativeTime.at($0))" } ?? "Goes out soon").font(.headline)
            Inset { Text(draft.text) }
            if let error {
                ErrorRow(text: error) { await reload() }
            }
            Button("Cancel") { Task { await unschedule(draft) } }
                .buttonStyle(.secondaryCapsule)
                .accessibilityLabel("Cancel this send")
                .disabled(busy)
        }
    }

    private func unschedule(_ draft: Draft) async {
        busy = true
        defer { busy = false }
        do {
            _ = try await client.unschedule(draftID: draft.id)
            error = nil
        } catch let late as APIError where late.status == 409 {
            toast = Toast(text: "Too late to cancel the message to \(card.name).")
        } catch {
            self.error = error.localizedDescription
        }
        await reload()
    }

    /// Send (or Retry), Send at, or Copy. Each first saves an edit.
    private func act(_ draft: Draft, send: Bool, at: Date? = nil) async {
        busy = true
        defer { busy = false }
        do {
            var current = draft
            if text != draft.text {
                current = try await client.saveEdit(draftID: draft.id, text: text)
                if current.deniesAI {
                    await reload()  // the edit still denies it: the reason shows again
                    return
                }
            }
            if let at, send {
                try await client.sendDraft(draftID: current.id, at: at)
                toast = Toast(text: "Goes to \(card.name) \(RelativeTime.at(at))")  // no Undo wait: Cancel is docked
                await reload()  // it docks as the scheduled send
            } else if send {
                try await client.sendDraft(draftID: current.id)
                toast = .sending(to: card.name) { Task { await undoSend(current) } }
                Task { await sent() }
            } else {
                UIPasteboard.general.string = current.text
                _ = try await client.copy(draftID: current.id)
                toast = Toast(text: "Copied. Paste it in \(datingApp).")
                await reload()  // it docks again as copied
            }
            error = nil
        } catch let refused as APIError where refused.status == 409 && send {
            error = "Not sent: \(datingApp) cannot send it now. Copy it instead."
            await reload()  // the draft comes back with Copy
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// The toast's Undo: the server takes the draft back while it still holds it, and it docks again as it was.
    private func undoSend(_ draft: Draft) async {
        do {
            _ = try await client.undoSend(draftID: draft.id)
        } catch let late as APIError where late.status == 409 {
            toast = Toast(text: "Too late to undo the message to \(card.name).")
        } catch {
            self.error = error.localizedDescription
        }
        await reload()
    }

    /// Send now: the planned send goes out at once, and the card reloads until it is in the chat.
    private func sendNow(_ planned: Draft) async {
        busy = true
        defer { busy = false }
        do {
            try await client.sendNow(draftID: planned.id)
            error = nil
            toast = Toast(text: "Sending to \(card.name)…")
            Task { await sent() }
        } catch let refused as APIError where refused.status == 409 {
            error = "Not sent now: it is already going out, or \(datingApp) cannot send it."
            await reload()
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Hold: the planned send does not go out. The draft docks again as pending, and waits in Review.
    private func hold(_ planned: Draft) async {
        busy = true
        defer { busy = false }
        do {
            _ = try await client.hold(draftID: planned.id)
            error = nil
            toast = Toast(text: "Held. It waits in Review.")
        } catch let late as APIError where late.status == 409 {
            toast = Toast(text: "Too late to hold the message to \(card.name).")
        } catch {
            self.error = error.localizedDescription
        }
        await reload()
    }

    /// Clear with Undo: the draft hides now and is dismissed on the server once Undo is over.
    private func clear(_ draft: Draft) {
        let held = Held {
            do {
                try await client.dismiss(draftID: draft.id)
            } catch {
                self.error = "The draft was not cleared. Check your connection, then clear it again."
            }
            await reload()
            clearing = nil
        }
        clearing = (draft.id, held)
        toast = Toast(text: "Cleared the draft for \(card.name)") {
            if held.undo() { clearing = nil }
        }
    }
}
