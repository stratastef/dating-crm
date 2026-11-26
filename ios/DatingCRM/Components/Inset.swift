import SwiftUI

/// Text on a solid surface inside a glass plate or the composer, where grey text and the AI marker stay readable.
struct Inset<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(Color(uiColor: .systemBackground), in: .rect(cornerRadius: 16))
    }
}
