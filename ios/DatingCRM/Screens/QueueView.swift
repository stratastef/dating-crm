import SwiftUI
import UIKit

/// Review: the review queue, cleared in a batch, hot leads first. Each item is led by the match's face, with what
/// the user needs to decide on a glass plate over it (ADR 0009). The match's name opens the card.
struct QueueView: View {
    let client: APIClient

    @State private var review: ReviewQueue
    @State private var toast: Toast?

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
                    if let draft = item.draft {
                        DraftItem(client: client, review: review, item: item, draft: draft) {
                            review.dismiss(item)
                            toast = Toast(text: "Dismissed the draft for \(item.cardName)") { review.undo(item) }
                        }
                    } else if item.kind == "handover", let cardID = item.cardID {
                        HandoverItem(client: client, review: review, item: item, cardID: cardID) {
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
    }
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
                // Glass on the background, not the content: glass would make the black Approve capsule grey.
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

/// Text on a solid surface inside a plate, where grey metadata stays readable.
private struct Inset<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color(uiColor: .systemBackground), in: .rect(cornerRadius: 16))
    }
}

private struct DraftItem: View {
    let client: APIClient
    let review: ReviewQueue
    let item: QueueItem
    let draft: Draft
    let dismiss: () -> Void

    @State private var text: String
    @State private var busy = false

    init(client: APIClient, review: ReviewQueue, item: QueueItem, draft: Draft, dismiss: @escaping () -> Void) {
        self.client = client
        self.review = review
        self.item = item
        self.draft = draft
        self.dismiss = dismiss
        _text = State(initialValue: draft.text)
    }

    var body: some View {
        PhotoCard(name: item.cardName, photo: item.card?.leadPhotoUrl) {
            ItemHeader(item: item)
            AdaptiveStack {
                Text("\(draft.kind == .opener ? "Opener" : "Reply") on \((item.card?.app ?? "").capitalized)")
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
            }
            AdaptiveStack(spacing: 8) {
                Button("Dismiss", action: dismiss)
                    .buttonStyle(.secondaryCapsule)
                Button("Approve") { approve() }
                    .buttonStyle(.primaryCapsule)
                    .disabled(text.isEmpty)
            }
            .disabled(busy)
        }
    }

    private func approve() {
        busy = true
        Task {
            defer { busy = false }
            do {
                if text != draft.text {
                    _ = try await client.saveEdit(draftID: draft.id, text: text)
                }
                try await client.approve(draftID: draft.id)
                review.remove(item)
                review.error = nil
            } catch {
                review.error = error.localizedDescription
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

    var body: some View {
        PhotoCard(name: item.cardName, photo: item.card?.leadPhotoUrl) {
            ItemHeader(item: item)
            // The symbol inline, not a Label's icon column, which takes a third of the width at accessibility sizes.
            Text("\(Image(systemName: "hand.raised")) \(Self.reason(item.triggers ?? []))")
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
    }

    /// Why autopilot stopped, from the server's trigger codes (`HANDOVER` in `app/jev.py`).
    static func reason(_ triggers: [String]) -> String {
        let reasons = triggers.map { trigger in
            switch trigger {
            case "asks_if_ai": "they asked if you're an AI"
            case "logistics": "they want to make plans"
            case "place_or_exclusivity": "they asked where to meet or about being exclusive"
            case "personal_info": "they shared or asked for personal info"
            case "sensitive": "they brought up something sensitive"
            case "unavailable": "the message could not be checked"
            default: "a handover trigger fired"
            }
        }
        guard !reasons.isEmpty else { return "Autopilot paused this chat" }
        return "Autopilot stopped: \(reasons.formatted())"
    }

    /// Either way the handover no longer waits in Review.
    private func change(takeOver: Bool) {
        busy = true
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
    }

    private func answer(approve: Bool) {
        busy = true
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
