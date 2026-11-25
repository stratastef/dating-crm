import SwiftUI

@main
struct DatingCRMApp: App {
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            if let client = session.client {
                BoardView(client: client, signOut: session.signOut)
            } else {
                SignInView(session: session)
            }
        }
    }
}
