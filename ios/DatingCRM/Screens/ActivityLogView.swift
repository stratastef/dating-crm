import SwiftUI

/// The Activity log: what the app did toward dating apps and the calendar, newest first, and what triggered each.
struct ActivityLogView: View {
    let client: APIClient

    @State private var entries: [ActivityEntry]?
    @State private var error: String?

    var body: some View {
        List {
            if let error {
                ErrorRow(text: error) { await load() }
            }
            if entries?.isEmpty == true {
                Text("Nothing yet. Each message, swipe, profile change and calendar hold the app makes shows up here.")
                    .fontDesign(.serif)
                    .foregroundStyle(.secondaryText)
            }
            ForEach(entries ?? []) { entry in
                VStack(alignment: .leading, spacing: 2) {
                    AdaptiveStack {
                        // Full width, so the time sits at the trailing edge, or under it at accessibility sizes.
                        Text(entry.summary).frame(maxWidth: .infinity, alignment: .leading)
                        TimeAgoText(date: entry.createdAt).font(.subheadline).foregroundStyle(.secondaryText)
                    }
                    Text(entry.app == "all" ? "All apps" : entry.app.capitalized)
                        .font(.subheadline)
                        .foregroundStyle(.secondaryText)
                    Text("Triggered by \(entry.trigger)")
                        .font(.footnote)
                        .foregroundStyle(.secondaryText)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .navigationTitle("Activity log")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        do {
            entries = try await client.activityLog()
            error = nil
        } catch {
            self.error = "Couldn't load the activity log. Tap to try again."
        }
    }
}
