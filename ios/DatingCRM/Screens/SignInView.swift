import SwiftUI

/// Sign-in: the phone number, then the sign-in code the server texts to it. A long press on the title opens the
/// developer sign-in (server URL and API token), for pointing the app at a local stack.
struct SignInView: View {
    let session: Session

    @State private var phone = "+"
    @State private var code = ""
    /// The number (E.164) the last code went to; nil while the user types their number.
    /// `DCRM_PHONE=+1…` opens the code step for scripted simulator checks (see `Session.init`). It sends nothing.
    @State private var codeSentTo = ProcessInfo.processInfo.environment["DCRM_PHONE"]
    @State private var codeSentAt = Date.now
    @State private var error: String?
    @State private var isWorking = false
    @State private var showsDeveloperSignIn = false

    /// How long the user waits before asking for a new code.
    private let resendWait: TimeInterval = 30

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text("Dating CRM")
                    .font(.largeTitle.bold())
                    .onLongPressGesture(minimumDuration: 2) { showsDeveloperSignIn = true }
                if let number = codeSentTo { codeStep(number) } else { phoneStep }
            }
            .padding(.horizontal, 20)
            .padding(.top, 48)
        }
        .scrollDismissesKeyboard(.interactively)
        .tint(.primary)
        .sheet(isPresented: $showsDeveloperSignIn) { DeveloperSignInView(session: session) }
    }

    private var phoneStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Sign in with your phone number. We'll text you your Dating CRM code.")
                .fontDesign(.serif)
            field("Phone number", text: $phone, prompt: "+1 415 555 0100")
                .keyboardType(.phonePad)
                .textContentType(.telephoneNumber)
            Text("Start with + and your country code.")
                .font(.footnote)
                .foregroundStyle(.secondaryText)
            errorLabel
            Button(isWorking ? "Sending…" : "Send code") { Task { await sendCode() } }
                .buttonStyle(.primaryCapsule)
                .disabled(phone.count < 2 || isWorking)
        }
    }

    private func codeStep(_ number: String) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("We texted your Dating CRM code to \(number). It is valid for 10 minutes.")
                .fontDesign(.serif)
            field("Your Dating CRM code", text: $code, prompt: "6 digits")
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .onChange(of: code) { _, typed in code = String(typed.filter(\.isNumber).prefix(6)) }
            errorLabel
            Button(isWorking ? "Signing in…" : "Sign in") { Task { await signIn(number) } }
                .buttonStyle(.primaryCapsule)
                .disabled(code.count != 6 || isWorking)
            TimelineView(.periodic(from: .now, by: 1)) { context in
                let wait = Int(codeSentAt.addingTimeInterval(resendWait).timeIntervalSince(context.date).rounded(.up))
                Button(wait > 0 ? "Send a new code in \(wait) s" : "Send a new code") {
                    phone = number
                    Task { await sendCode() }
                }
                .buttonStyle(.secondaryCapsule)
                .disabled(wait > 0 || isWorking)
            }
            Button("Use another number") {
                codeSentTo = nil
                code = ""
                error = nil
            }
            .frame(maxWidth: .infinity, minHeight: 44)
        }
    }

    /// A labelled text field, 52 pt high. The label above it is for the eye; VoiceOver reads the field's title.
    private func field(_ label: String, text: Binding<String>, prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .accessibilityHidden(true)
            TextField(label, text: text, prompt: Text(prompt).foregroundStyle(.secondaryText))
                .font(.title3)
                .padding(.horizontal, 16)
                .frame(minHeight: 52)
                // Not `tertiarySystemFill`: the grey prompt would fall just under 4.5:1 on it in light mode.
                .background(Color(uiColor: .secondarySystemBackground), in: .rect(cornerRadius: 12))
        }
    }

    /// The last refusal, in plain words, under the field it is about.
    @ViewBuilder private var errorLabel: some View {
        if let error {
            Label(error, systemImage: "exclamationmark.circle.fill")
                .font(.subheadline)
                .foregroundStyle(Color.primary)
        }
    }

    private func sendCode() async {
        guard let number = Session.e164(phone) else {
            error = "Enter your number with its country code, such as +1 415 555 0100."
            return
        }
        isWorking = true
        defer { isWorking = false }
        do {
            try await session.requestCode(phone: number)
            codeSentTo = number
            codeSentAt = .now
            code = ""
            error = nil
        } catch {
            self.error = message(for: error, [
                403: "No account has this number yet. You need an invite code to create one.",
                422: "Enter your number with its country code, such as +1 415 555 0100.",
                429: "Too many codes were sent to this number. Try again in an hour.",
            ])
        }
    }

    private func signIn(_ number: String) async {
        isWorking = true
        defer { isWorking = false }
        do {
            try await session.signIn(phone: number, code: code)
        } catch {
            self.error = message(for: error, [
                401: "That code is wrong. Check the text and try again.",
                410: "That code has expired. Send a new code.",
                429: "Too many tries with this code. Send a new code.",
            ])
        }
    }

    private func message(for error: Error, _ byStatus: [Int: String]) -> String {
        (error as? APIError).flatMap { byStatus[$0.status] }
            ?? "Dating CRM could not be reached. Check your connection and try again."
    }
}

/// The developer sign-in: any server URL and an API token from `python -m app.auth`.
private struct DeveloperSignInView: View {
    let session: Session

    @Environment(\.dismiss) private var dismiss
    @State private var serverURL = ""
    @State private var token = ""
    @State private var error: String?
    @State private var isSigningIn = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("Server URL", text: $serverURL, prompt: Text("http://localhost:8000"))
                        .keyboardType(.URL)
                        .textContentType(.URL)
                    SecureField("API token", text: $token)
                } footer: {
                    Text("Paste the address of your server and the API token it printed for you.")
                }
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()

                if let error {
                    Label(error, systemImage: "exclamationmark.circle.fill").foregroundStyle(Color.primary)
                }

                Button(isSigningIn ? "Signing in…" : "Sign in") {
                    Task { await signIn() }
                }
                .disabled(serverURL.isEmpty || token.isEmpty || isSigningIn)
            }
            .navigationTitle("Developer sign-in")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
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
