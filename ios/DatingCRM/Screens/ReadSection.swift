import SwiftUI

/// The match read on a card: each inference with its evidence and confidence word (Sure, Likely, Guess), and a tap
/// to correct it.
struct ReadSection: View {
    let client: APIClient
    let cardID: Int

    @State private var read: [Inference] = []
    @State private var reading = false
    @State private var correcting: Inference?
    @State private var correction = ""
    @State private var error: String?

    var body: some View {
        Section {
            if let error {
                ErrorRow(text: error) { await load { try await client.read(cardID: cardID) } }
            }
            ForEach(read) { inference in
                Button {
                    correction = inference.text
                    correcting = inference
                } label: {
                    VStack(alignment: .leading, spacing: 3) {
                        AdaptiveStack(spacing: 6) {
                            Text(inference.title).font(.subheadline.weight(.semibold))
                            Text(inference.corrected == nil ? inference.confidenceWord : "Corrected by you")
                                .font(.subheadline)
                                .foregroundStyle(.secondaryText)
                        }
                        Text(inference.text)
                        Text("Evidence: \(inference.evidence)").font(.subheadline).foregroundStyle(.secondaryText)
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(.rect)
                }
                .accessibilityHint("Corrects this inference")
            }
            Button(read.isEmpty ? "Read match" : "Read again", systemImage: "sparkles") {
                Task { await load { try await client.makeRead(cardID: cardID) } }
            }
            .frame(minHeight: 44)
            .disabled(reading)
        } header: {
            Text("Match read").foregroundStyle(Color.primary)
        }
        .task {
            await load { try await client.read(cardID: cardID) }
        }
        .alert("Correct \(correcting?.title.lowercased() ?? "")", isPresented: isCorrecting) {
            TextField("Correction", text: $correction)
            Button("Save") {
                Task { await saveCorrection() }
            }
            Button("Cancel", role: .cancel) {}
        }
    }

    private var isCorrecting: Binding<Bool> {
        Binding(get: { correcting != nil }, set: { if !$0 { correcting = nil } })
    }

    private func load(_ fetch: () async throws -> [Inference]) async {
        reading = true
        defer { reading = false }
        do {
            read = try await fetch()
            error = nil
        } catch {
            self.error = "The match read did not load. Check your connection, then tap to try again."
        }
    }

    private func saveCorrection() async {
        guard let inference = correcting, !correction.isEmpty else { return }
        do {
            let corrected = try await client.correct(inferenceID: inference.id, text: correction)
            read = read.map { $0.id == corrected.id ? corrected : $0 }
            error = nil
        } catch {
            self.error = "The correction was not saved. Check your connection, then correct it again."
        }
    }
}
