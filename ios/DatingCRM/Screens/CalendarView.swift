import AuthenticationServices
import SwiftUI

/// Google Calendar: whether it is connected, and Connect, so every time slot offered to a match gets a hold.
/// Under You; the setup step shows the same view.
struct CalendarView: View {
    let client: APIClient

    @State private var consentPage = ConsentPage()
    @State private var connected: Bool?
    @State private var connecting = false
    @State private var refused: String?  // why the last Connect left it not connected
    @State private var error: String?
    @State private var toast: Toast?

    var body: some View {
        List {
            if let error {
                ErrorRow(text: error, retry: load)
            }
            if let connected {
                VStack(alignment: .leading, spacing: 10) {
                    Text("Google Calendar").font(.headline)
                    if connected {
                        Text("Connected. Every time slot the app offers a match is held in your calendar, so no two matches get the same evening.")
                            .foregroundStyle(.secondaryText)
                        Button("Reconnect") { Task { await connect() } }.buttonStyle(.secondaryCapsule).disabled(connecting)
                    } else {
                        Text("Not connected. Connect it so every time slot the app offers a match is held in your calendar.")
                            .fontDesign(.serif).foregroundStyle(.secondaryText)
                        if let refused {
                            Label(refused, systemImage: "exclamationmark.circle").foregroundStyle(Color.primary)
                        }
                        Button("Connect") { Task { await connect() } }.buttonStyle(.primaryCapsule).disabled(connecting)
                    }
                }
                .padding(.vertical, 6)
                .alignmentGuide(.listRowSeparatorLeading) { $0[.leading] }  // not inset to the refusal label's text
            }
        }
        .navigationTitle("Calendar")
        .task { await load() }
        .refreshable { await load() }
        .toast($toast)
    }

    /// Opens Google's consent page. Google returns to the server, the server to the app, and the app then asks the
    /// server whether the calendar is connected.
    private func connect() async {
        connecting = true
        defer { connecting = false }
        do {
            let consent = try await client.calendarConsentURL()
            let returned = try await consentPage.open(consent)
            let connected = try await client.calendarConnected()
            self.connected = connected
            if !connected {
                refused = "Google didn't give access. Connect again and choose Allow."
            } else if returned.query == nil {  // the server adds `?error=` when Google refused: a refused Reconnect
                refused = nil
                toast = Toast(text: "Google Calendar connected.")
            }
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            refused = "You closed Google's page before allowing access."
        } catch is ASWebAuthenticationSessionError {
            refused = "Google's page didn't open. Try again."
        } catch let error as APIError where error.status == 503 {
            refused = "The server isn't set up for Google Calendar yet. It needs a Google OAuth client."
        } catch {
            refused = error.localizedDescription
        }
    }

    private func load() async {
        do {
            connected = try await client.calendarConnected()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// Google's consent page in a web authentication session, which ends when the server sends it to `datingcrm://`.
/// Not SwiftUI's `webAuthenticationSession`: on the iOS 27 simulator it failed at once with
/// `presentationContextNotProvided`.
private final class ConsentPage: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?  // kept while the page is open

    /// The `datingcrm://calendar` address the server sent the session to.
    func open(_ url: URL) async throws -> URL {
        defer { session = nil }
        return try await withCheckedThrowingContinuation { done in
            let session = ASWebAuthenticationSession(url: url, callback: .customScheme("datingcrm")) { returned, error in
                if let returned { done.resume(returning: returned) } else { done.resume(throwing: error!) }
            }
            session.presentationContextProvider = self
            // Ephemeral: no "wants to use google.com to sign in" alert, and no Google cookies kept in the app.
            session.prefersEphemeralWebBrowserSession = true
            self.session = session
            session.start()
        }
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scene = UIApplication.shared.connectedScenes.lazy.compactMap { $0 as? UIWindowScene }.first!  // Connect was tapped in it
        return scene.keyWindow ?? UIWindow(windowScene: scene)
    }
}
