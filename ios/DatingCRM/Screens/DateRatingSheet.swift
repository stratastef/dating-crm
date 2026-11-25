import SwiftUI

/// Asks for a 1–5 rating and a short note when a card reaches Dated.
struct DateRatingSheet: View {
    let name: String
    let onRated: (Int, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var rating = 3
    @State private var note = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("How was the date with \(name)?") {
                    Picker("Rating", selection: $rating) {
                        ForEach(1...5, id: \.self) { Text("\($0)").tag($0) }
                    }
                    .pickerStyle(.segmented)
                    TextField("Short note", text: $note, axis: .vertical)
                }
            }
            .navigationTitle("Rate the date")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Not now") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        onRated(rating, note)
                        dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }
}
