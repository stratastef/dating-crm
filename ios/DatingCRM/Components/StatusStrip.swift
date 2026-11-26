import SwiftUI

/// The status strip: the tab view's bottom accessory, on Liquid Glass, while something stops autopilot. It shows
/// the first of the server's messages (`GET /status`, in priority order): a pause with Resume, the AI budget with
/// the day it resets, or a broken connector with Reconnect, which opens Connected apps. Hidden when there is none.
/// Apply it to the `TabView` itself.
struct StatusStrip: ViewModifier {
    let client: APIClient
    /// The selected tab: the strip reloads on every tab change, and every minute.
    let tab: MainTabView.AppTab

    @State private var message: StatusMessage?
    @State private var reconnecting = false
    @State private var loaded = false
    @State private var haptic: Haptic?

    func body(content: Content) -> some View {
        Group {
            if #available(iOS 26.1, *) {
                content.tabViewBottomAccessory(isEnabled: message != nil) { strip }
            } else if message != nil {
                // shortcut: iOS 26.0 cannot hide an accessory, so the tab view is rebuilt when the strip comes or
                // goes and the tabs lose their place. Drop this branch once the deployment target is 26.1.
                content.tabViewBottomAccessory { strip }
            } else {
                content
            }
        }
        .task(id: tab) {
            // A budget reached or a connector broken on the server shows within a minute.
            repeat { await load() } while (try? await Task.sleep(for: .seconds(60))) != nil
        }
        .haptic(haptic)
        .sheet(isPresented: $reconnecting, onDismiss: { Task { await load() } }) {
            NavigationStack {
                ConnectedAppsView(client: client)
                    .toolbar { Button("Done") { reconnecting = false } }
            }
        }
    }

    @ViewBuilder private var strip: some View {
        if let message {
            HStack(spacing: 10) {
                Image(systemName: icon(message))
                    .foregroundStyle(.accent)  // the strip waits on the user
                    .accessibilityHidden(true)
                Text(text(message))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .accessibilityShowsLargeContentViewer()
                Spacer(minLength: 0)
                switch message.kind {
                case .paused:
                    action("Resume") {
                        haptic = Haptic(.press)  // a pause turned off
                        _ = try? await client.setPaused(false, app: message.app)
                        await load()
                    }
                case .connectorAlert:
                    action("Reconnect") { reconnecting = true }
                case .budgetReached:
                    EmptyView()
                }
            }
            .font(.subheadline)
            // The accessory's height is fixed, like the tab bar's: larger text would truncate. Long press shows
            // the text in the Large Content Viewer instead.
            .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .padding(.leading, 16)
            .padding(.trailing, 6)
        }
    }

    private func text(_ message: StatusMessage) -> String {
        let app = message.app?.capitalized
        return switch message.kind {
        case .paused: app.map { "\($0) paused" } ?? "Autopilot paused"
        case .budgetReached: "AI budget reached. Resets \(message.resetsAt.map { RelativeTime.day($0) } ?? "next month")"
        case .connectorAlert: "\(app ?? "A dating app") disconnected"
        }
    }

    private func icon(_ message: StatusMessage) -> String {
        switch message.kind {
        case .paused: "pause.fill"
        case .budgetReached: "dollarsign.circle"
        case .connectorAlert: "exclamationmark.triangle"
        }
    }

    private func action(_ title: String, _ run: @escaping () async -> Void) -> some View {
        Button(title) { Task { await run() } }
            .fontWeight(.semibold)
            .padding(.horizontal, 10)
            .frame(minWidth: 44, minHeight: 44)
    }

    /// A failed load keeps the last strip: the screens show their own errors.
    private func load() async {
        guard let messages = try? await client.status() else { return }
        // Not on the first load: a strip that was already there at launch is no news.
        if loaded && Self.fails(from: message, to: messages.first) { haptic = Haptic(.fail) }
        message = messages.first
        loaded = true
    }

    /// Fail plays when the strip starts to say the AI budget is reached or a connector signed out. A pause is the
    /// user's own doing.
    static func fails(from old: StatusMessage?, to new: StatusMessage?) -> Bool {
        guard let new, new.kind != .paused else { return false }
        return new.kind != old?.kind || new.app != old?.app
    }
}
