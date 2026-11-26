import SwiftUI

/// The date's rating as one list section: 1 to 5, each with a short anchor so a rating means the same thing each
/// time, 4 and 5 marked as a good date. Nothing is selected while `rating` is nil. The rating sheet and the card's
/// Details tab use it.
struct RatingPicker: View {
    let title: String
    @Binding var rating: Int?

    static let anchors = [
        1: "Bad: I won't see them again",
        2: "Meh: probably not again",
        3: "Fine: not sure about another",
        4: "Good: I'd like another date",
        5: "Great: I want another date soon",
    ]

    var body: some View {
        Section {
            ForEach(1...5, id: \.self) { value in
                Button {
                    rating = value
                } label: {
                    HStack(spacing: 14) {
                        Text("\(value)").font(.title2.bold()).monospacedDigit()
                        VStack(alignment: .leading, spacing: 2) {
                            Text(Self.anchors[value] ?? "")
                            if value >= 4 {
                                Text("Good date").font(.footnote).foregroundStyle(.secondaryText)
                            }
                        }
                        Spacer(minLength: 0)
                        if rating == value {
                            Image(systemName: "checkmark").fontWeight(.semibold)
                        }
                    }
                    .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                    .contentShape(.rect)
                }
                .accessibilityLabel("\(value), \(Self.anchors[value] ?? "")\(value >= 4 ? ", good date" : "")")
                .accessibilityAddTraits(rating == value ? .isSelected : [])
            }
        } header: {
            Text(title).foregroundStyle(Color.primary)
        } footer: {
            Text("Good = rated 4 or 5.").foregroundStyle(.secondaryText)
        }
    }
}
