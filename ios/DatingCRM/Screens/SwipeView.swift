import SwiftUI

/// Swipe copilot: the server suggests like or pass for each profile, and the user decides every one.
struct SwipeView: View {
    let client: APIClient

    // shortcut: Tinder is the only app with a connector. Add a picker when a second one can swipe.
    private let app = "tinder"

    @State private var candidates: [SwipeCandidate] = []
    @State private var loaded = false
    @State private var busy = false
    @State private var error: String?
    @State private var notice: String?

    var body: some View {
        List {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            if let notice {
                Text(notice).foregroundStyle(.secondaryText)
            }
            if loaded && candidates.isEmpty {
                ContentUnavailableView("No profiles waiting", systemImage: "person.2",
                                       description: Text("Tap Find profiles to get suggestions.").foregroundStyle(.secondaryText))
                    .fontDesign(.serif)
            }
            ForEach(candidates) { candidate in
                CandidateRow(candidate: candidate) { swipe in
                    await decide(candidate, swipe)
                }
            }
        }
        .navigationTitle("Swipe")
        .toolbar {
            Button("Find profiles") {
                Task { await load { try await client.suggestSwipes(app: app) } }
            }
            .disabled(busy)
        }
        .refreshable { await load { try await client.swipes() } }
        .task { await load { try await client.swipes() } }
    }

    private func load(_ fetch: () async throws -> [SwipeCandidate]) async {
        busy = true
        do {
            candidates = try await fetch()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
        busy = false
        loaded = true
    }

    private func decide(_ candidate: SwipeCandidate, _ swipe: Swipe) async {
        do {
            let applied = try await client.swipe(candidateID: candidate.id, swipe)
            candidates.removeAll { $0.id == candidate.id }
            error = nil
            notice = applied ? nil : "Saved your \(swipe.rawValue) on \(candidate.name). \(candidate.app.capitalized) could not be reached: swipe there by hand."
        } catch {
            self.error = error.localizedDescription
        }
    }
}

private struct CandidateRow: View {
    let candidate: SwipeCandidate
    let decide: (Swipe) async -> Void

    @State private var busy = false

    var body: some View {
        Section(candidate.name) {
            if !candidate.photos.isEmpty {
                ScrollView(.horizontal) {
                    HStack {
                        ForEach(candidate.photos, id: \.self) { photo in
                            AsyncImage(url: photo) { image in
                                image.resizable().scaledToFill()
                            } placeholder: {
                                Color.secondary.opacity(0.2)
                            }
                            .frame(width: 150, height: 200)
                            .clipShape(.rect(cornerRadius: 8))
                            .accessibilityLabel("Photo of \(candidate.name)")
                        }
                    }
                }
            }
            if !candidate.bio.isEmpty {
                Text(candidate.bio)
            }
            VStack(alignment: .leading) {
                AIMarker(.suggests)
                Text(candidate.suggestion.title).font(.headline)
                Text(candidate.reason).font(.subheadline).foregroundStyle(.secondaryText)
            }
            HStack {
                swipeButton(.pass, systemImage: "xmark")
                Spacer()
                swipeButton(.like, systemImage: "heart")
            }
            // Without this, a tap anywhere in the row triggers both buttons.
            .buttonStyle(.borderless)
            .disabled(busy)
        }
    }

    private func swipeButton(_ swipe: Swipe, systemImage: String) -> some View {
        Button(swipe.title, systemImage: systemImage) {
            busy = true
            Task {
                await decide(swipe)
                busy = false
            }
        }
        // The suggested swipe stands out; the other one is the override.
        .fontWeight(swipe == candidate.suggestion ? .bold : .regular)
    }
}
