import SwiftUI

/// The Swipe layout choice (ADR 0004) as one list section that loads and saves the setting itself. Under You, and
/// for the setup step.
struct SwipeLayoutSection: View {
    let client: APIClient

    @State private var layout: SwipeLayout?
    @State private var error: String?

    var body: some View {
        Section {
            if let error {
                ErrorRow(text: error) { await load() }
            }
            Picker("Swipe layout", selection: Binding { layout } set: { choose($0) }) {
                ForEach(SwipeLayout.allCases) { layout in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(layout.title)
                        Text(layout.summary)
                            .font(.subheadline)
                            .foregroundStyle(.secondaryText)
                    }
                    .tag(SwipeLayout?.some(layout))
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } header: {
            Text("Swipe layout").foregroundStyle(Color.primary)
        } footer: {
            Text("Until you choose, Swipe shows one at a time. You can change it here at any time.")
                .fontDesign(.serif)
                .foregroundStyle(.secondaryText)
        }
        .task { await load() }
    }

    private func load() async {
        do {
            layout = try await client.swipeLayout()
            error = nil
        } catch {
            self.error = "Couldn't load your Swipe layout. Tap to try again."
        }
    }

    private func choose(_ choice: SwipeLayout?) {
        guard let choice else { return }
        let before = layout
        layout = choice
        Task {
            do {
                layout = try await client.setSwipeLayout(choice)
                error = nil
            } catch {
                layout = before
                self.error = "Couldn't save your Swipe layout. Tap to try again."
            }
        }
    }
}
