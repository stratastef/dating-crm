import SwiftUI

/// Connected apps: each dating app's connector state, with Connect or Reconnect, and the choice to keep an app
/// copilot-only. Under You; the setup step shows the same view.
struct ConnectedAppsView: View {
    let client: APIClient

    @State private var apps: [ConnectedApp] = []
    @State private var error: String?
    @State private var connecting: ConnectedApp?
    @State private var choosingCopilotOnly: ConnectedApp?
    @State private var toast: Toast?

    var body: some View {
        List {
            if let error {
                ErrorRow(text: error, retry: load)
            }
            ForEach(apps) { app in
                row(app)
            }
        }
        .navigationTitle("Connected apps")
        .task { await load() }
        .refreshable { await load() }
        .sheet(item: $connecting) { app in
            ConnectAppSheet(client: client, app: app.app) {
                toast = Toast(text: "\(app.app.capitalized) connected. Syncing now.")
                Task { await load() }
            }
        }
        .confirmationDialog(
            "Keep \(choosingCopilotOnly?.app.capitalized ?? "") copilot-only?",
            isPresented: Binding { choosingCopilotOnly != nil } set: { if !$0 { choosingCopilotOnly = nil } },
            titleVisibility: .visible,
            presenting: choosingCopilotOnly
        ) { app in
            Button("Copilot only") {
                Task { await run { try await client.chooseCopilotOnly(app: app.app) } }
            }
        } message: { app in
            Text("""
            Nothing syncs, sends or swipes on \(app.app.capitalized), and the server forgets its session token. \
            The app drafts and you copy. Connect again any time.
            """)
        }
        .toast($toast)
    }

    private func row(_ app: ConnectedApp) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            AdaptiveStack {
                // Full width, so the time sits at the trailing edge, or under the name at accessibility sizes.
                Text(app.app.capitalized).font(.headline).frame(maxWidth: .infinity, alignment: .leading)
                if let alert = app.alert {
                    TimeAgoText(date: alert.createdAt).font(.subheadline).foregroundStyle(.secondaryText)
                }
            }
            status(app)
            AdaptiveStack(spacing: 10) {
                switch app.state {
                case .notConnected:
                    Button("Connect") { connecting = app }.buttonStyle(.primaryCapsule)
                    copilotOnlyButton(app)
                case .broken:
                    Button("Reconnect") { connecting = app }.buttonStyle(.primaryCapsule)
                    copilotOnlyButton(app)
                case .connected:
                    Button("Reconnect") { connecting = app }.buttonStyle(.secondaryCapsule)
                    copilotOnlyButton(app)
                case .copilotOnly:
                    Button("Connect") { connecting = app }.buttonStyle(.secondaryCapsule)
                case .noConnector:
                    EmptyView()
                }
            }
        }
        .padding(.vertical, 6)
        .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }  // not inset to the warning label's text
    }

    @ViewBuilder private func status(_ app: ConnectedApp) -> some View {
        let name = app.app.capitalized
        switch app.state {
        case .connected:
            Text("Connected. Matches sync every 15 minutes, and Send works.").foregroundStyle(.secondaryText)
        case .broken:
            // A broken connector waits on the user, so it takes the accent.
            Label(brokenText(app.alert, name: name), systemImage: "exclamationmark.triangle").foregroundStyle(.accent)
            explanation("Reconnecting does not resume autopilot. Resume it under Autopilot.")
        case .copilotOnly:
            explanation("Copilot only. The app drafts and you copy. Connect to sync and send again.")
        case .notConnected:
            explanation("Not connected. Paste a session token to sync matches and send from here.")
        case .noConnector:
            explanation("No connector yet. The app drafts for \(name) and you copy each message into \(name).")
        }
    }

    private func brokenText(_ alert: ConnectorAlert?, name: String) -> String {
        let why = alert?.reason == "ban signal" ? "\(name) refused the account, which can mean a ban" : "\(name) ended the session"
        return "Stopped working: \(why)."
    }

    private func copilotOnlyButton(_ app: ConnectedApp) -> some View {
        Button("Copilot only") { choosingCopilotOnly = app }.buttonStyle(.secondaryCapsule)
    }

    private func explanation(_ text: String) -> some View {
        Text(text).fontDesign(.serif).foregroundStyle(.secondaryText)
    }

    private func load() async {
        await run {}
    }

    /// Runs one server call, then reloads the states. A failure shows on top of the list.
    private func run(_ action: () async throws -> Void) async {
        do {
            try await action()
            apps = try await client.connectedApps()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}
