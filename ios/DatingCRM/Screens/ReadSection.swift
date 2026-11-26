import SwiftUI

/// The match read on a card: each inference with its evidence and confidence, and a way to correct it.
struct ReadSection: View {
    let client: APIClient
    let cardID: Int

    @State private var read: [Inference] = []
    @State private var reading = false
    @State private var correcting: Inference?
    @State private var correction = ""
    @State private var error: String?

    var body: some View {
        Section("Match read") {
            if let error {
                Text(error).foregroundStyle(.red)
            }
            ForEach(read) { inference in
                Button {
                    correction = inference.text
                    correcting = inference
                } label: {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(inference.title).font(.caption).foregroundStyle(.secondaryText)
                            Spacer()
                            Text(inference.corrected == nil ? "\(Int((inference.confidence * 100).rounded()))% sure" : "Corrected by you")
                                .font(.caption)
                                .foregroundStyle(.secondaryText)
                        }
                        Text(inference.text).foregroundStyle(.primary)
                        Text("Evidence: \(inference.evidence)").font(.caption).foregroundStyle(.secondaryText)
                    }
                }
                .accessibilityHint("Corrects this inference")
            }
            Button(read.isEmpty ? "Read match" : "Read again", systemImage: "sparkles") {
                Task { await load { try await client.makeRead(cardID: cardID) } }
            }
            .disabled(reading)
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
            self.error = error.localizedDescription
        }
    }

    private func saveCorrection() async {
        guard let inference = correcting, !correction.isEmpty else { return }
        do {
            let corrected = try await client.correct(inferenceID: inference.id, text: correction)
            read = read.map { $0.id == corrected.id ? corrected : $0 }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
