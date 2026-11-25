import SwiftUI

struct SignInView: View {
    let session: Session

    @State private var serverURL = ""
    @State private var token = ""
    @State private var error: String?
    @State private var isSigningIn = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Server URL", text: $serverURL, prompt: Text("https://crm.example.com"))
                        .keyboardType(.URL)
                        .textContentType(.URL)
                    SecureField("API token", text: $token)
                } footer: {
                    Text("Paste the address of your server and the API token it printed for you.")
                }
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()

                if let error {
                    Text(error).foregroundStyle(.red)
                }

                Button(isSigningIn ? "Signing in…" : "Sign in") {
                    Task { await signIn() }
                }
                .disabled(serverURL.isEmpty || token.isEmpty || isSigningIn)
            }
            .navigationTitle("Dating CRM")
        }
    }

    private func signIn() async {
        isSigningIn = true
        defer { isSigningIn = false }
        do {
            try await session.signIn(serverURL: serverURL, token: token)
        } catch {
            self.error = error.localizedDescription
        }
    }
}
