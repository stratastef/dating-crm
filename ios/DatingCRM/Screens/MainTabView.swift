import SwiftUI

/// The app once signed in: five tabs, opening on Today (ADR 0005). Each tab has its own navigation stack.
struct MainTabView: View {
    enum AppTab: String { case today, review, pipeline, swipe, you }

    let client: APIClient
    let push: Push
    let signOut: () async throws -> Void

    // `DCRM_TAB=review` opens another tab, for scripted simulator checks (see `Session.init`).
    @State private var selection = AppTab(rawValue: ProcessInfo.processInfo.environment["DCRM_TAB"] ?? "") ?? .today
    // From Today's review summary.
    @State private var reviewCount = 0
    @AppStorage(BlurredFace.key) private var blurPhotos = false

    var body: some View {
        TabView(selection: $selection) {
            Tab("Today", systemImage: "calendar", value: .today) {
                TodayView(client: client, openReview: { selection = .review }, reviewCount: $reviewCount)
            }
            Tab("Review", systemImage: "checklist", value: .review) {
                NavigationStack { QueueView(client: client) }
            }
            .badge(reviewCount)
            Tab("Pipeline", systemImage: "person.2", value: .pipeline) {
                PipelineView(client: client, push: push)
            }
            Tab("Swipe", systemImage: "rectangle.stack", value: .swipe) {
                NavigationStack { SwipeView(client: client) }
            }
            Tab("You", systemImage: "person.crop.circle", value: .you) {
                NavigationStack { YouView(client: client, signOut: signOut) }
            }
        }
        .modifier(StatusStrip(client: client, tab: selection))
        // Black and white: buttons, links and the selected tab never take the accent.
        .tint(.primary)
        .listStyle(.plain)
        .modifier(MotionReducedReader())
        // A tapped push opens its card, which the Pipeline shows.
        .onChange(of: push.openedCardID, initial: true) { _, id in
            if id != nil { selection = .pipeline }
        }
        // Blur photos is the server's setting; a change made on another phone shows from the next launch.
        .task {
            if let settings = try? await client.settings() { blurPhotos = settings.blurPhotos }
        }
    }
}
