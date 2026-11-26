import SwiftUI
import UIKit

/// Review: the review queue, cleared in a batch, hot leads first. Each item is led by the match's face, with what
/// the user needs to decide on a glass plate over it (ADR 0009). The match's name opens the card.
struct QueueView: View {
    let client: APIClient

    @State private var review: ReviewQueue
    @State private var toast: Toast?
    /// For actions that take their item off the screen at once, so the item cannot play it.
    @State private var haptic: Haptic?

    init(client: APIClient) {
        self.client = client
        _review = State(initialValue: ReviewQueue(client: client))
    }

    var body: some View {
        ScrollView {
            LazyVStack(spacing: 14) {
                if let error = review.error {
                    ErrorRow(text: error) { await review.load() }
                }
                if review.loaded && review.items.isEmpty {
                    ContentUnavailableView("Nothing to review", systemImage: "checkmark.circle")
                        .fontDesign(.serif)
                }
                ForEach(review.items) { item in
                    // Kinds this version does not know are not shown.
                    if item.kind == "draft" || item.kind == "failed_send", let draft = item.draft {
                        DraftItem(client: client, review: review, item: item, draft: draft) {
                            haptic = Haptic(.tap)
                            review.dismiss(item)
                            toast = Toast(text: "Dismissed the draft for \(item.cardName)") { review.undo(item) }
                        } copied: {
                            toast = Toast(text: "Copied. Paste it in \(item.datingApp).")
                        } sent: { at in
                            review.remove(item)
                            let undo: () -> Void = { Task { await review.undoSend(item) } }
                            if let at {  // Send at: no Undo wait, so no ring; Undo takes the scheduled send back
                                toast = Toast(text: "Goes to \(item.cardName) \(RelativeTime.at(at))", undo: undo)
                            } else {
                                toast = .sending(to: item.cardName, undo: undo)
                            }
                        }
                    } else if item.kind == "copied_draft", let draft = item.draft {
                        CopiedDraftItem(item: item, draft: draft) {
                            haptic = Haptic(.tap)
                            UIPasteboard.general.string = draft.text
                            toast = Toast(text: "Copied. Paste it in \(item.datingApp).")
                        } clear: {
                            haptic = Haptic(.tap)
                            review.dismiss(item)
                            toast = Toast(text: "Cleared the draft for \(item.cardName)") { review.undo(item) }
                        }
                    } else if item.kind == "handover", let cardID = item.cardID {
                        HandoverItem(client: client, review: review, item: item, cardID: cardID) {
                            haptic = Haptic(.tap)
                            toast = Toast(text: "Copied")
                        }
                    } else if let paidItem = item.paidItem {
                        PaidItemCard(client: client, review: review, item: item, paidItem: paidItem)
                    }
                }
            }
            .padding(.horizontal, 14)
        }
        .navigationTitle("Review")
        .navigationDestination(for: Card.self) { card in
            CardDetailView(client: client, card: card) { _ in }
        }
        .refreshable { await review.load() }
        .task { await review.load() }
        .toast($toast)
        .haptic(haptic)
        // The user cleared the last waiting item: Today's count is at zero.
        .sensoryFeedback(.done, trigger: review.cleared)
    }
}

private extension QueueItem {
    /// Where the user pastes a copied draft: "Hinge".
    var datingApp: String { card.map { $0.app.capitalized } ?? "the dating app" }
}

/// A face filling the item, with the plate on Liquid Glass over its lower part: the one place glass sits on
/// content (ADR 0009).
private struct PhotoCard<Plate: View>: View {
    let name: String
    let photo: URL?
    @ViewBuilder let plate: Plate

    var body: some View {
        VStack(alignment: .leading, spacing: 10) { plate }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background {
                // The fill keeps the plate's text at 4.5:1 over any photo, so plates use `.primary` text only.
                // Glass on the background, not the content: glass would make the black Send capsule grey.
                RoundedRectangle(cornerRadius: 24)
                    .fill(Color(uiColor: .systemBackground).opacity(0.72))
                    .glassEffect(.regular, in: .rect(cornerRadius: 24))
            }
            .padding(10)
            .padding(.top, 200)  // the face shows above the plate
            .background { FacePhoto(name: name, photo: photo) }
            .clipShape(.rect(cornerRadius: 30))
    }
}

/// The match's name, which opens the card, and the hot-lead badge.
private struct ItemHeader: View {
    let item: QueueItem
    var name: String? = nil

    var body: some View {
        AdaptiveStack(spacing: 8) {
            Group {
                if let card = item.card {
                    NavigationLink(value: card) {
                        Text(name ?? item.cardName)
                            .multilineTextAlignment(.leading)  // a link's label centers a name that wraps
                    }
                    .accessibilityHint("Opens the card")
                } else {
                    Text(name ?? item.cardName)
                }
            }
            .font(.title2.bold())
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            if item.hot {
                // On the soft accent: the accent alone is under 4.5:1 on glass.
                Badge(.hot)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(.accentSoft, in: .capsule)
            }
        }
    }
}

/// The match's message, quoted.
private struct Quote: View {
    let message: QuotedMessage

    var body: some View {
        Text("“\(message.body)”").lineLimit(6)
    }
}

/// A pending draft, with the action named for its effect (ADR 0003): Send where the app can send it, Copy where
/// it cannot. Its suggested send time shows in the draft, with Send at next to Send. A failed send shows the same
/// way, with Retry and Copy.
private struct DraftItem: View {
    let client: APIClient
    let review: ReviewQueue
    let item: QueueItem
    let dismiss: () -> Void
    let copied: () -> Void
    /// After Send (nil) or Send at (the time).
    let sent: (Date?) -> Void

    @State private var draft: Draft
    @State private var text: String
    @State private var busy = false
    @State private var haptic: Haptic?

    init(
        client: APIClient, review: ReviewQueue, item: QueueItem, draft: Draft,
        dismiss: @escaping () -> Void, copied: @escaping () -> Void, sent: @escaping (Date?) -> Void
    ) {
        self.client = client
        self.review = review
        self.item = item
        self.dismiss = dismiss
        self.copied = copied
        self.sent = sent
        _draft = State(initialValue: draft)
        _text = State(initialValue: draft.text)
    }

    /// It denies being AI and the user has not changed it: neither sent nor copied until they do.
    private var waitsForEdit: Bool { draft.deniesAI && text == draft.text }

    private var failed: Bool { item.kind == "failed_send" }

    /// When Send at would send it: a pending draft the app can send, with its suggested time still ahead.
    private var sendAt: Date? { failed || waitsForEdit || !draft.sendable ? nil : draft.suggestedSendAt }

    var body: some View {
        PhotoCard(name: item.cardName, photo: item.card?.leadPhotoUrl) {
            ItemHeader(item: item)
            AdaptiveStack {
                Text("\(draft.kind == .opener ? "Opener" : "Reply") on \(item.datingApp)")
                if let message = item.message {
                    TimeAgoText(date: message.sentAt)
                }
            }
            .font(.subheadline)
            if let message = item.message {
                Quote(message: message)
            }
            Inset {
                AIMarker(.draft)
                TextField("Draft", text: $text, axis: .vertical)
                    .lineLimit(2...)
                if !failed {
                    SuggestedSendTime(draft: draft)
                }
            }
            if waitsForEdit {
                Text("\(Image(systemName: "exclamationmark.triangle")) It says you're not an AI. Edit it before you send it.")
            }
            if failed {
                // The app's error may have come after the message reached the match.
                Text("\(Image(systemName: "exclamationmark.triangle")) Sending failed. It may still have reached \(item.datingApp), so check the chat before you send it again.")
            }
            Group {
                if let sendAt {
                    // Three capsules side by side where they fit (the default text size); else Send at goes above.
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 8) { secondary; sendAtButton(sendAt); primary }
                        VStack(spacing: 8) {
                            sendAtButton(sendAt)
                            AdaptiveStack(spacing: 8) { secondary; primary }
                        }
                    }
                } else {
                    AdaptiveStack(spacing: 8) { secondary; primary }
                }
            }
            .disabled(busy)
        }
        .haptic(haptic)
    }

    @ViewBuilder private var secondary: some View {
        if failed {
            Button("Copy") { act(send: false) }
                .buttonStyle(.secondaryCapsule)
        } else {
            Button("Dismiss", action: dismiss)
                .buttonStyle(.secondaryCapsule)
        }
    }

    @ViewBuilder private var primary: some View {
        // A failed send the app cannot retry now offers Copy only.
        if !waitsForEdit, draft.sendable || !failed {
            Button(failed ? "Retry" : draft.sendable ? "Send" : "Copy") { act(send: draft.sendable) }
                .buttonStyle(.primaryCapsule)
                .disabled(text.isEmpty)
        }
    }

    private func sendAtButton(_ at: Date) -> some View {
        SendAtButton(at: at) { act(send: true, at: at) }
            .disabled(text.isEmpty)
    }

    private func act(send: Bool, at: Date? = nil) {
        busy = true
        haptic = Haptic(send ? .press : .tap)
        Task {
            defer { busy = false }
            do {
                if text != draft.text {
                    draft = try await client.saveEdit(draftID: draft.id, text: text)
                    if draft.deniesAI { return }  // the edit still denies it: the reason shows again
                }
                if send {
                    try await client.sendDraft(draftID: draft.id, at: at)
                    sent(at)
                } else {
                    UIPasteboard.general.string = draft.text
                    _ = try await client.copy(draftID: draft.id)
                    copied()
                    await review.load()  // it waits on as a copied draft
                }
                review.error = nil
            } catch {
                if send { haptic = Haptic(.fail) }
                review.error = error.localizedDescription
            }
        }
    }
}

/// A draft the user copied. It waits until their message shows up in the chat, or they clear it (ADR 0003).
private struct CopiedDraftItem: View {
    let item: QueueItem
    let draft: Draft
    let copyAgain: () -> Void
    let clear: () -> Void

    var body: some View {
        PhotoCard(name: item.cardName, photo: item.card?.leadPhotoUrl) {
            ItemHeader(item: item)
            Text("Copied for \(item.datingApp), not sent yet")
            Inset {
                Text(draft.text)
                SuggestedSendTime(draft: draft)  // when to paste it
            }
            if draft.deniesAI {
                Text("\(Image(systemName: "exclamationmark.triangle")) It says you're not an AI. Clear it and write another.")
            }
            AdaptiveStack(spacing: 8) {
                Button("Clear", action: clear)
                    .buttonStyle(.secondaryCapsule)
                if !draft.deniesAI {
                    Button("Copy again", action: copyAgain)
                        .buttonStyle(.primaryCapsule)
                }
            }
        }
    }
}

private struct HandoverItem: View {
    let client: APIClient
    let review: ReviewQueue
    let item: QueueItem
    let cardID: Int
    let copied: () -> Void

    @State private var busy = false
    @State private var haptic: Haptic?

    var body: some View {
        PhotoCard(name: item.cardName, photo: item.card?.leadPhotoUrl) {
            ItemHeader(item: item)
            // The symbol inline, not a Label's icon column, which takes a third of the width at accessibility sizes.
            Text("\(Image(systemName: "hand.raised")) \(HandoverBanner.reason(item.triggers ?? []))")
            if let message = item.message {
                Quote(message: message)
            }
            if let suggestions = item.suggestions, !suggestions.isEmpty {
                Inset {
                    AIMarker(.suggests)
                    ForEach(suggestions, id: \.self) { suggestion in
                        HStack {
                            Text(suggestion).frame(maxWidth: .infinity, alignment: .leading)
                            Button("Copy", systemImage: "doc.on.doc") {
                                UIPasteboard.general.string = suggestion
                                copied()
                            }
                            .labelStyle(.iconOnly)
                            .frame(minWidth: 44, minHeight: 44)
                            .accessibilityLabel("Copy “\(suggestion)”")
                        }
                    }
                }
            }
            AdaptiveStack(spacing: 8) {
                Button("Hand back") { change(takeOver: false) }
                    .buttonStyle(.secondaryCapsule)
                Button("Take over") { change(takeOver: true) }
                    .buttonStyle(.primaryCapsule)
            }
            .disabled(busy)
        }
        .haptic(haptic)
    }

    /// Either way the handover no longer waits in Review.
    private func change(takeOver: Bool) {
        busy = true
        haptic = Haptic(takeOver ? .press : .tap)
        Task {
            defer { busy = false }
            do {
                if takeOver {
                    try await client.takeOver(cardID: cardID)
                } else {
                    try await client.handBack(cardID: cardID)
                }
                review.remove(item)
                review.error = nil
            } catch {
                review.error = error.localizedDescription
            }
        }
    }
}

/// A paid item the server proposes to spend. Nothing is spent until the user approves.
private struct PaidItemCard: View {
    let client: APIClient
    let review: ReviewQueue
    let item: QueueItem
    let paidItem: PaidItem

    @State private var busy = false
    @State private var showsProfile = false
    @State private var approvals = 0

    var body: some View {
        PhotoCard(name: paidItem.name, photo: paidItem.photoUrl) {
            ItemHeader(item: item, name: paidItem.name)
            AdaptiveStack {
                Label(paidItem.title, systemImage: "star.circle")
                if let cost = paidItem.cost {
                    Text(cost)
                }
            }
            .font(.subheadline.weight(.semibold))
            if !paidItem.reason.isEmpty {
                Text(paidItem.reason)
            }
            if paidItem.candidateID != nil {
                Button("See \(paidItem.name)'s profile", systemImage: "person.crop.rectangle") { showsProfile = true }
                    .frame(minHeight: 44)
            }
            AdaptiveStack(spacing: 8) {
                Button("Decline") { answer(approve: false) }
                    .buttonStyle(.secondaryCapsule)
                Button("Approve") { answer(approve: true) }
                    .buttonStyle(.primaryCapsule)
            }
            .disabled(busy)
        }
        .sheet(isPresented: $showsProfile) {
            if let candidateID = paidItem.candidateID {
                CandidateProfile(client: client, candidateID: candidateID)
            }
        }
        .sensoryFeedback(.thud, trigger: approvals)
    }

    private func answer(approve: Bool) {
        busy = true
        if approve { approvals += 1 }
        Task {
            defer { busy = false }
            do {
                if approve {
                    if try await client.approve(paidItemID: paidItem.id).status != "spent" {
                        // It no longer waits on the server, so only the message stays until the next refresh.
                        review.error = "Not spent: the app was not reached or the account has none left."
                        return
                    }
                } else {
                    try await client.decline(paidItemID: paidItem.id)
                }
                review.remove(item)
                review.error = nil
            } catch {
                review.error = error.localizedDescription
            }
        }
    }
}

/// The profile a paid item is for: its photos and bio, as the dating app showed them.
private struct CandidateProfile: View {
    let client: APIClient
    let candidateID: Int

    @Environment(\.dismiss) private var dismiss
    @State private var candidate: SwipeCandidate?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let error {
                        ErrorRow(text: error) { await load() }
                    }
                    if let candidate {
                        ForEach(candidate.photos, id: \.self) { photo in
                            FacePhoto(name: candidate.name, photo: photo)
                                .aspectRatio(3 / 4, contentMode: .fit)
                                .clipShape(.rect(cornerRadius: 24))
                        }
                        if !candidate.bio.isEmpty {
                            Text(candidate.bio)
                        }
                    } else if error == nil {
                        ProgressView().frame(maxWidth: .infinity)
                    }
                }
                .padding(.horizontal, 14)
            }
            .navigationTitle(candidate?.name ?? "Profile")
            .toolbar {
                Button("Done") { dismiss() }
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            // The profile waits for a swipe as long as the paid item waits, so it is among the waiting ones.
            candidate = try await client.swipes().first { $0.id == candidateID }
            error = candidate == nil ? "This profile no longer waits for a swipe." : nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
