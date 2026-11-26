import SwiftUI

/// A person's face in a row: the lead photo at 48 pt, or their initial in New York on the soft accent.
struct Avatar: View {
    let name: String
    let photo: URL?

    var body: some View {
        // With no photo, while it loads and if it fails, the monogram shows.
        AsyncImage(url: photo) { image in
            image.resizable().scaledToFill()
        } placeholder: {
            Text(name.prefix(1).uppercased())
                .font(.system(size: 21, weight: .semibold, design: .serif))
                .foregroundStyle(.accent)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(.accentSoft)
        }
        .frame(width: 48, height: 48)
        .clipShape(.circle)
        // In a list row, the separator starts past the avatar, under the text 14 pt after it.
        .alignmentGuide(.listRowSeparatorLeading) { $0[.trailing] + 14 }
        // The row says the name.
        .accessibilityHidden(true)
    }
}
