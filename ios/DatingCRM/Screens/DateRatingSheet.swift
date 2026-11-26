import SwiftUI

/// Asks for the date's rating and a short note. It opens from the card on reaching Dated, from Today's dates to rate
/// and from the Pipeline's "Rate the date" rows. Nothing is selected at first, so Save waits for a real choice.
struct DateRatingSheet: View {
    let name: String
    let onRated: (Int, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var rating: Int?
    @State private var note = ""
    @State private var lowRatings = 0

    var body: some View {
        NavigationStack {
            List {
                RatingPicker(title: "How was the date with \(name)?", rating: $rating)
                Section {
                    GrowingField(label: "Note", prompt: "What stood out", text: $note)
                } header: {
                    Text("Note").foregroundStyle(Color.primary)
                }
            }
            .scrollDismissesKeyboard(.immediately)
            .navigationTitle("Rate the date")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Not now") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        if let rating {
                            // A good date is the brand moment. A lower one gets no celebration and no punishment.
                            if rating >= 4 { HourRing.play() } else { lowRatings += 1 }
                            onRated(rating, note)
                        }
                        dismiss()
                    }
                    .disabled(rating == nil)
                }
            }
        }
        .sensoryFeedback(.tap, trigger: lowRatings)
    }
}
