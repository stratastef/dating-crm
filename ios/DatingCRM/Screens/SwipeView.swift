import SwiftUI

/// Swipe copilot: the server suggests like or pass for each swipe candidate, and the user decides every one, in the
/// Swipe layout they chose (ADR 0004): one at a time, or a list. A swipe waits out the toast before it is sent, so
/// Undo leaves nothing on the dating app. With swiping Off, the tab says how to turn it on.
struct SwipeView: View {
    let client: APIClient

    // shortcut: Tinder is the only app with a connector. Add a picker when a second one can swipe.
    private let app = "tinder"

    @State private var candidates: [SwipeCandidate] = []
    @State private var layout: SwipeLayout?
    @State private var swiping: AutonomyLevel?
    @State private var loaded = false
    @State private var busy = false
    @State private var error: String?
    @State private var notice: String?
    @State private var toast: Toast?
    /// Swiped here, but the swipe waits out the toast: a reload must not show them again.
    @State private var held: Set<Int> = []
    /// Swiped since the last load, for "2 of 4".
    @State private var done = 0
    @State private var enlarged: Photo?

    var body: some View {
        Group {
            if swiping == .off {
                off
            } else if layout == .list {
                list
            } else {
                oneAtATime
            }
        }
        .navigationTitle("Swipe")
        .toolbar {
            if loaded && swiping != .off {
                Button("Find profiles") {
                    Task { await load { try await client.suggestSwipes(app: app) } }
                }
                .disabled(busy)
            }
        }
        .fullScreenCover(item: $enlarged) { photo in
            FullScreenPhoto(photo: photo)
        }
        // Again on every return to the tab: the level or layout may have changed under You.
        .task { await refresh() }
    }

    // MARK: Off

    private var off: some View {
        // Scrolls only when it does not fit, at the largest text sizes, so the link stays reachable.
        ViewThatFits(in: .vertical) {
            offExplanation
            ScrollView { offExplanation }
        }
    }

    private var offExplanation: some View {
        ContentUnavailableView {
            Label("Swiping is off", systemImage: "rectangle.stack")
        } description: {
            Text("""
            Set Swipe to Copilot under Autopilot: the app suggests like or pass for each profile, and you decide. \
            On Autopilot it swipes alone, within your swipe limits.
            """)
            .foregroundStyle(.secondaryText)
        } actions: {
            NavigationLink("Open Autopilot") { AutopilotView(client: client) }
                .buttonStyle(.primaryCapsule)
                .fontDesign(.default)
        }
        .fontDesign(.serif)
    }

    // MARK: One at a time

    private var oneAtATime: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                messages
                if let candidate = candidates.first {
                    Text("\(done + 1) of \(done + candidates.count)")
                        .font(.subheadline)
                        .foregroundStyle(.secondaryText)
                    CandidateCard(candidate: candidate, enlarge: { enlarged = $0 }, answer: answer)
                } else if loaded {
                    empty
                }
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 24)
        }
        .refreshable { await refresh() }
        // Before the bar, so the toast sits above Pass and Like instead of over them.
        .toast($toast)
        .safeAreaBar(edge: .bottom) {
            if let candidate = candidates.first {
                SwipeButtons(suggestion: candidate.suggestion) { decide([(candidate, $0)]) }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    // Opaque: the Pass capsule's fill is translucent and would show the text scrolling under it.
                    .background(Color(uiColor: .systemBackground))
            }
        }
    }

    // MARK: List

    private var list: some View {
        List {
            messages
            if !candidates.isEmpty {
                Button("Accept all suggestions") { decide(candidates.map { ($0, $0.suggestion) }) }
                    .buttonStyle(.primaryCapsule)
                    .listRowSeparator(.hidden)
            }
            ForEach(candidates) { candidate in
                CandidateRow(candidate: candidate) { decide([(candidate, $0)]) }
            }
            if loaded && candidates.isEmpty {
                empty
            }
        }
        .refreshable { await refresh() }
        .toast($toast)
    }

    // MARK: Shared

    @ViewBuilder private var messages: some View {
        if let error {
            ErrorRow(text: error) { await refresh() }
        }
        if let notice {
            Text(notice).foregroundStyle(.secondaryText)
        }
    }

    private var empty: some View {
        ContentUnavailableView("No profiles waiting", systemImage: "person.2",
                               description: Text("Tap Find profiles to get suggestions.").foregroundStyle(.secondaryText))
            .fontDesign(.serif)
    }

    private func refresh() async {
        await load {
            swiping = try await client.autonomy()["swipe"] ?? .off
            layout = try await client.swipeLayout()
            return try await client.swipes()
        }
    }

    private func load(_ fetch: () async throws -> [SwipeCandidate]) async {
        busy = true
        do {
            candidates = try await fetch().filter { !held.contains($0.id) }
            done = 0
            error = nil
        } catch {
            self.error = "Couldn't load the profiles. Tap to try again."
        }
        busy = false
        loaded = true
    }

    /// Takes the candidates off the screen now and sends the swipes when the toast is gone, unless Undo comes first.
    private func decide(_ decisions: [(candidate: SwipeCandidate, swipe: Swipe)]) {
        let ids = Set(decisions.map(\.candidate.id))
        candidates.removeAll { ids.contains($0.id) }
        held.formUnion(ids)
        done += decisions.count
        let send = Held { await send(decisions) }
        toast = Toast(text: Self.toastText(decisions)) {
            guard send.undo() else { return }  // too late: already on the dating app
            held.subtract(ids)
            done -= decisions.count
            restore(decisions.map(\.candidate))
        }
    }

    private func send(_ decisions: [(candidate: SwipeCandidate, swipe: Swipe)]) async {
        for (candidate, swipe) in decisions {
            do {
                if try await !client.swipe(candidateID: candidate.id, swipe) {
                    notice = """
                    Saved your \(swipe.rawValue) on \(candidate.name). \(candidate.app.capitalized) could not be \
                    reached: swipe there by hand.
                    """
                }
            } catch {
                self.error = "Couldn't send your \(swipe.rawValue) on \(candidate.name). Tap to try again."
                done -= 1
                restore([candidate])
            }
            held.remove(candidate.id)
        }
    }

    /// Puts candidates back in the server's order, oldest first.
    private func restore(_ back: [SwipeCandidate]) {
        candidates = (candidates + back).sorted { $0.id < $1.id }
    }

    /// The user's answer to the Super Like proposed for a candidate. A spent one is the swipe, so the candidate goes.
    private func answer(_ candidate: SwipeCandidate, approve: Bool) async {
        guard let item = candidate.paidItem else { return }
        do {
            if approve {
                if try await client.approve(paidItemID: item.id).status == "spent" {
                    candidates.removeAll { $0.id == candidate.id }
                    done += 1
                    toast = Toast(text: "Super Liked \(candidate.name)")
                    return
                }
                notice = "Super Like not spent: \(candidate.app.capitalized) was not reached or the account has none left."
            } else {
                try await client.decline(paidItemID: item.id)
            }
            if let index = candidates.firstIndex(of: candidate) {
                candidates[index].paidItem = nil
            }
            error = nil
        } catch {
            self.error = "Couldn't answer the Super Like. Tap to reload."
        }
    }

    static func toastText(_ decisions: [(candidate: SwipeCandidate, swipe: Swipe)]) -> String {
        guard decisions.count == 1, let first = decisions.first else {
            return "Accepted \(decisions.count) suggestions"
        }
        return first.swipe == .like ? "Liked \(first.candidate.name)" : "Passed on \(first.candidate.name)"
    }
}

/// One photo of a candidate, to show full screen.
private struct Photo: Identifiable {
    let url: URL
    let name: String
    var id: URL { url }
}

/// One at a time: the photos full width with the name on glass, the AI's suggestion, the proposed Super Like and
/// the bio. Pass and Like are buttons in a bar under it; there is no drag gesture.
private struct CandidateCard: View {
    let candidate: SwipeCandidate
    let enlarge: (Photo) -> Void
    let answer: (SwipeCandidate, Bool) async -> Void

    @State private var answering = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            photos
                // Short enough that the suggestion shows above Pass and Like without scrolling.
                .frame(height: 400)
                .clipShape(.rect(cornerRadius: 30))
                .overlay(alignment: .bottom) { plate }
            VStack(alignment: .leading, spacing: 4) {
                AIMarker(.suggests)
                Text("\(Text(candidate.suggestion.title).bold()). \(candidate.reason)")
            }
            if let item = candidate.paidItem {
                superLike(item)
            }
            if !candidate.bio.isEmpty {
                Text(candidate.bio)
            }
        }
    }

    @ViewBuilder private var photos: some View {
        if candidate.photos.isEmpty {
            Text(candidate.name.prefix(1).uppercased())
                .font(.system(size: 96, weight: .semibold, design: .serif))
                .foregroundStyle(.accent)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                .padding(.top, 40)
                .background(.accentSoft)
                .accessibilityHidden(true)
        } else {
            TabView {
                ForEach(Array(candidate.photos.enumerated()), id: \.element) { index, url in
                    Button {
                        enlarge(Photo(url: url, name: candidate.name))
                    } label: {
                        AsyncImage(url: url) { image in
                            image.resizable().scaledToFill().blurredFace()
                        } placeholder: {
                            Color(uiColor: .secondarySystemBackground)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipped()
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Photo \(index + 1) of \(candidate.photos.count) of \(candidate.name)")
                    .accessibilityHint("Shows it full screen")
                }
            }
            .tabViewStyle(.page(indexDisplayMode: candidate.photos.count > 1 ? .always : .never))
        }
    }

    private var plate: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(candidate.nameAndAge)
                .font(.title2.weight(.semibold))
            Text(candidate.details).font(.subheadline)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .glassEffect(.regular, in: .rect(cornerRadius: 22))
        .padding(10)
        // Above the page dots, which sit at the bottom of the photos.
        .padding(.bottom, candidate.photos.count > 1 ? 24 : 0)
        .accessibilityElement(children: .combine)
    }

    private func superLike(_ item: PaidItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Super Like proposed", systemImage: "star")
                .font(.headline)
            if !item.reason.isEmpty {
                Text(item.reason).foregroundStyle(.secondaryText)
            }
            Text("It spends a Super Like your account holds.")
                .font(.subheadline)
                .fontDesign(.serif)
                .foregroundStyle(.secondaryText)
            AdaptiveStack(spacing: 8) {
                Button("Not now") { reply(approve: false) }
                    .buttonStyle(.secondaryCapsule)
                Button("Super Like", systemImage: "star") { reply(approve: true) }
                    .buttonStyle(.secondaryCapsule)
            }
            .disabled(answering)
        }
        .padding(14)
        .background(Color(uiColor: .secondarySystemBackground), in: .rect(cornerRadius: 18))
    }

    private func reply(approve: Bool) {
        answering = true
        Task {
            await answer(candidate, approve)
            answering = false
        }
    }
}

/// Pass and Like as two capsules. The suggested one is filled: preselected, and the other is the override.
private struct SwipeButtons: View {
    let suggestion: Swipe
    let decide: (Swipe) -> Void

    var body: some View {
        AdaptiveStack(spacing: 8) {
            button(.pass, systemImage: "xmark")
            button(.like, systemImage: "heart")
        }
    }

    @ViewBuilder private func button(_ swipe: Swipe, systemImage: String) -> some View {
        let button = Button(swipe.title, systemImage: systemImage) { decide(swipe) }
        if swipe == suggestion {
            button.buttonStyle(.primaryCapsule).accessibilityHint("Suggested by AI")
        } else {
            button.buttonStyle(.secondaryCapsule)
        }
    }
}

/// The list: a candidate as a row with the face, the AI's suggestion and its reason, and Pass and Like with the
/// suggestion preselected.
private struct CandidateRow: View {
    let candidate: SwipeCandidate
    let decide: (Swipe) -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Avatar(name: candidate.name, photo: candidate.photos.first)
            VStack(alignment: .leading, spacing: 6) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(candidate.nameAndAge).font(.headline)
                    Text(candidate.details).font(.subheadline).foregroundStyle(.secondaryText)
                }
                .accessibilityElement(children: .combine)
                VStack(alignment: .leading, spacing: 2) {
                    AIMarker(.suggests)
                    Text("\(Text(candidate.suggestion.title).bold()). \(candidate.reason)")
                        .font(.subheadline)
                }
                if candidate.paidItem != nil {
                    Label("Super Like proposed: answer it in Review", systemImage: "star")
                        .font(.subheadline)
                }
                SwipeButtons(suggestion: candidate.suggestion, decide: decide)
            }
        }
        .padding(.vertical, 4)
    }
}

/// One photo on black, scaled to fit, with Close.
private struct FullScreenPhoto: View {
    let photo: Photo
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        AsyncImage(url: photo.url) { image in
            image.resizable().scaledToFit()
        } placeholder: {
            ProgressView().tint(.white)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(.black)
        .accessibilityLabel("Photo of \(photo.name)")
        .overlay(alignment: .topTrailing) {
            Button("Close", systemImage: "xmark") { dismiss() }
                .labelStyle(.iconOnly)
                .font(.title3)
                .frame(width: 44, height: 44)
                .glassEffect(.regular, in: .circle)
                .padding(16)
        }
    }
}
