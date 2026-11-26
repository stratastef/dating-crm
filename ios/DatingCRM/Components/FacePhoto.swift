import SwiftUI

/// A face that fills its frame: the photo, or the person's initial in New York on the soft accent (ADR 0009).
/// For Review items and the card header; rows use `Avatar`.
struct FacePhoto: View {
    let name: String
    let photo: URL?

    var body: some View {
        // With no photo, while it loads and if it fails, the monogram shows.
        Color.accentSoft
            .overlay {
                AsyncImage(url: photo) { image in
                    image.resizable().scaledToFill().blurredFace()
                } placeholder: {
                    Text(name.prefix(1).uppercased())
                        .font(.system(size: 96, weight: .semibold, design: .serif))
                        .foregroundStyle(.accent)
                        .padding(.top, 18)
                        .frame(maxHeight: .infinity, alignment: .top)
                }
            }
            .clipped()
            // The item says the name.
            .accessibilityHidden(true)
    }
}
