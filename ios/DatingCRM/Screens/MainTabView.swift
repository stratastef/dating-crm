import SwiftUI

/// The app once signed in: five tabs, opening on Today (ADR 0005). Each tab has its own navigation stack.
struct MainTabView: View {
    enum AppTab: String { case today, review, pipeline, swipe, you }

    let client: APIClient
    let push: Push
    let signOut: () async -> Void

    // `DCRM_TAB=review` opens another tab, for scripted simulator checks (see `Session.init`).
    @State private var selection = AppTab(rawValue: ProcessInfo.processInfo.environment["DCRM_TAB"] ?? "") ?? .today

    var body: some View {
        TabView(selection: $selection) {
            Tab("Today", systemImage: "calendar", value: .today) {
                // shortcut: a placeholder until the Today screen lands.
                NavigationStack {
                    ContentUnavailableView(
                        "Your day will be here", systemImage: "calendar",
                        description: Text("Overdue, today and coming up. Until then, the Pipeline has every card.")
                            .foregroundStyle(.secondaryText)
                    )
                    .fontDesign(.serif)
                    .navigationTitle("Today")
                }
            }
            Tab("Review", systemImage: "checklist", value: .review) {
                NavigationStack { QueueView(client: client) }
            }
            Tab("Pipeline", systemImage: "person.2", value: .pipeline) {
                BoardView(client: client, push: push)
            }
            Tab("Swipe", systemImage: "rectangle.stack", value: .swipe) {
                NavigationStack { SwipeView(client: client) }
            }
            Tab("You", systemImage: "person.crop.circle", value: .you) {
                NavigationStack { YouView(client: client, signOut: signOut) }
            }
        }
        // Black and white: buttons, links and the selected tab never take the accent.
        .tint(.primary)
        .listStyle(.plain)
        .modifier(MotionReducedReader())
        // A tapped push opens its card, which the Pipeline shows.
        .onChange(of: push.openedCardID, initial: true) { _, id in
            if id != nil { selection = .pipeline }
        }
    }
}
