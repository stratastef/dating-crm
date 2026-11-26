import Foundation
import Observation
import Security

enum SignInError: LocalizedError {
    case invalidServerURL

    var errorDescription: String? { "Enter the server URL, starting with https:// or http://." }
}

/// Who is signed in. `client` is nil until the user signs in, and is restored on launch.
/// The server URL is kept in `UserDefaults`; the API token only in the Keychain.
///
/// The share extension reads the same session. The URL is in the App Group's defaults. The token needs no
/// code: both targets list the same Keychain access group first in their entitlements, which makes it the
/// group a new item is stored in.
@Observable final class Session {
    private(set) var client: APIClient?

    private let keychainService: String
    private let defaults: UserDefaults
    private let transport: APIClient.Transport?
    private let serverURLKey = "serverURL"

    init(keychainService: String = "DatingCRM", defaults: UserDefaults = .appGroup, transport: APIClient.Transport? = nil) {
        self.keychainService = keychainService
        self.defaults = defaults
        self.transport = transport
        #if DEBUG
        // Simulator checks sign in without typing: `SIMCTL_CHILD_DCRM_SERVER=http://localhost:8047
        // SIMCTL_CHILD_DCRM_TOKEN=… xcrun simctl launch <udid> com.datingcrm.app`. Nothing is stored.
        let environment = ProcessInfo.processInfo.environment
        if let url = environment["DCRM_SERVER"].flatMap(URL.init(string:)), let token = environment["DCRM_TOKEN"] {
            client = makeClient(url, token)
            return
        }
        #endif
        if let url = defaults.url(forKey: serverURLKey), let token = storedToken() {
            client = makeClient(url, token)
        }
    }

    /// Checks the URL and token with one request to the server, then keeps them.
    func signIn(serverURL: String, token: String) async throws {
        guard let url = URL(string: serverURL.trimmingCharacters(in: .whitespacesAndNewlines)),
              ["http", "https"].contains(url.scheme), url.host() != nil
        else { throw SignInError.invalidServerURL }
        let candidate = makeClient(url, token.trimmingCharacters(in: .whitespacesAndNewlines))
        _ = try await candidate.cards()
        storeToken(candidate.token)
        defaults.set(url, forKey: serverURLKey)
        client = candidate
    }

    func signOut() {
        storeToken(nil)
        defaults.removeObject(forKey: serverURLKey)
        client = nil
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

extension UserDefaults {
    /// The defaults the app and its share extension share: those of the App Group named by `AppGroup` in Info.plist.
    static var appGroup: UserDefaults {
        (Bundle.main.object(forInfoDictionaryKey: "AppGroup") as? String).flatMap(UserDefaults.init(suiteName:)) ?? .standard
    }
}
