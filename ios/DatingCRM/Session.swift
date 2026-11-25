import Foundation
import Observation
import Security

enum SignInError: LocalizedError {
    case invalidServerURL

    var errorDescription: String? { "Enter the server URL, starting with https:// or http://." }
}

/// Who is signed in. `client` is nil until the user signs in, and is restored on launch.
/// The server URL is kept in `UserDefaults`; the API token only in the Keychain.
@Observable final class Session {
    private(set) var client: APIClient?

    private let keychainService: String
    private let defaults: UserDefaults
    private let transport: APIClient.Transport?
    private let serverURLKey = "serverURL"

    init(keychainService: String = "DatingCRM", defaults: UserDefaults = .standard, transport: APIClient.Transport? = nil) {
        self.keychainService = keychainService
        self.defaults = defaults
        self.transport = transport
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
