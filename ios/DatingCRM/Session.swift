import Foundation
import Observation
import Security

enum SignInError: LocalizedError {
    case invalidServerURL

    var errorDescription: String? { "Enter the server URL, starting with https:// or http://." }
}

/// Who is signed in. `client` is nil until the user signs in, and is restored on launch.
/// The user signs in with a phone number and a sign-in code, against the server named by `ServerURL` in Info.plist.
/// The developer sign-in takes any server URL and token instead. Either way the server URL is kept in
/// `UserDefaults` and this device's API token only in the Keychain.
///
/// The share extension reads the same session. The URL is in the App Group's defaults. The token needs no
/// code: both targets list the same Keychain access group first in their entitlements, which makes it the
/// group a new item is stored in.
@Observable final class Session {
    private(set) var client: APIClient?
    /// True when the last phone number sign-in created the account, so setup runs next. Not kept across launches.
    var isNewAccount = false

    private let keychainService: String
    private let defaults: UserDefaults
    private let transport: APIClient.Transport?
    /// The server the phone number sign-in goes to.
    private var serverURL: URL
    private let serverURLKey = "serverURL"

    init(
        keychainService: String = "DatingCRM", defaults: UserDefaults = .appGroup, transport: APIClient.Transport? = nil,
        serverURL: URL = .bundledServer
    ) {
        self.keychainService = keychainService
        self.defaults = defaults
        self.transport = transport
        self.serverURL = serverURL
        #if DEBUG
        // Simulator checks sign in without typing: `SIMCTL_CHILD_DCRM_SERVER=http://localhost:8047
        // SIMCTL_CHILD_DCRM_TOKEN=… xcrun simctl launch <udid> com.datingcrm.app`. Nothing is stored.
        // `DCRM_SERVER` alone points the phone number sign-in at that server.
        let environment = ProcessInfo.processInfo.environment
        // `DCRM_SETUP` (any value, or a step such as `voice`) opens setup as if this sign-in created the account.
        isNewAccount = environment["DCRM_SETUP"] != nil
        if let url = environment["DCRM_SERVER"].flatMap(URL.init(string:)) {
            self.serverURL = url
            if let token = environment["DCRM_TOKEN"] {
                client = makeClient(url, token)
                return
            }
        }
        #endif
        if let url = defaults.url(forKey: serverURLKey), let token = storedToken() {
            client = makeClient(url, token)
        }
    }

    /// The number as the server wants it (E.164): `+` and digits. A leading `00` counts as `+`. Nil without a
    /// country code, or with too few or too many digits.
    static func e164(_ typed: String) -> String? {
        var text = typed.trimmingCharacters(in: .whitespaces)
        if text.hasPrefix("00") { text = "+" + text.dropFirst(2) }
        let digits = text.filter { $0.isASCII && $0.isNumber }
        guard text.hasPrefix("+"), (7...15).contains(digits.count), digits.first != "0" else { return nil }
        return "+" + digits
    }

    /// Texts a sign-in code to the phone number (E.164). A number with no account needs an invite code.
    func requestCode(phone: String, inviteCode: String? = nil) async throws {
        try await makeClient(serverURL, "").requestSignInCode(phone: phone, inviteCode: inviteCode)
    }

    /// Trades the phone number and the sign-in code for this device's API token, then keeps it.
    func signIn(phone: String, code: String) async throws {
        let signedIn = try await makeClient(serverURL, "").signIn(phone: phone, code: code)
        isNewAccount = signedIn.newAccount
        keep(makeClient(serverURL, signedIn.token))
    }

    /// The developer sign-in: checks the URL and token with one request to the server, then keeps them.
    func signIn(serverURL: String, token: String) async throws {
        guard let url = URL(string: serverURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(url.scheme), url.host() != nil
        else { throw SignInError.invalidServerURL }
        let candidate = makeClient(url, token.trimmingCharacters(in: .whitespacesAndNewlines))
        _ = try await candidate.cards()
        keep(candidate)
    }

    /// Revokes this device's token on the server, which also stops its pushes, then forgets the session.
    /// The app signs out even when the server cannot be reached.
    func signOut() async {
        try? await client?.signOut()
        storeToken(nil)
        defaults.removeObject(forKey: serverURLKey)
        client = nil
    }

    /// The share extension reads what this stores: the URL from the App Group's defaults, the token from the Keychain.
    private func keep(_ candidate: APIClient) {
        storeToken(candidate.token)
        defaults.set(candidate.baseURL, forKey: serverURLKey)
        client = candidate
    }

    private func makeClient(_ url: URL, _ token: String) -> APIClient {
        var client = APIClient(baseURL: url, token: token)
        if let transport { client.transport = transport }
        return client
    }

    // MARK: Keychain

    private var tokenItem: [CFString: Any] {
        [kSecClass: kSecClassGenericPassword, kSecAttrService: keychainService, kSecAttrAccount: "api-token"]
    }

    private func storedToken() -> String? {
        var result: CFTypeRef?
        let query = tokenItem.merging([kSecReturnData: true, kSecMatchLimit: kSecMatchLimitOne]) { $1 }
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func storeToken(_ token: String?) {
        SecItemDelete(tokenItem as CFDictionary)
        guard let token else { return }
        let item = tokenItem.merging([
            kSecValueData: Data(token.utf8),
            kSecAttrAccessible: kSecAttrAccessibleAfterFirstUnlock,
        ]) { $1 }
        SecItemAdd(item as CFDictionary, nil)
    }
}

extension URL {
    /// The server named by `ServerURL` in the app's Info.plist.
    static var bundledServer: URL {
        (Bundle.main.object(forInfoDictionaryKey: "ServerURL") as? String).flatMap(URL.init(string:))
            ?? URL(string: "http://localhost:8000")!
    }
}

extension UserDefaults {
    /// The defaults the app and its share extension share: those of the App Group named by `AppGroup` in Info.plist.
    static var appGroup: UserDefaults {
        (Bundle.main.object(forInfoDictionaryKey: "AppGroup") as? String).flatMap(UserDefaults.init(suiteName:)) ?? .standard
    }
}
