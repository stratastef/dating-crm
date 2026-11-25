import Observation
import UIKit
import UserNotifications

/// Push notification state: the device token Apple gave this phone, and the card of a tapped push.
@Observable final class Push {
    /// The APNs device token in hex. Nil until Apple has answered.
    private(set) var deviceToken: String?
    /// The card of the push the user tapped. `takeOpenedCard` clears it.
    private(set) var openedCardID: Int?

    func received(deviceToken: Data) {
        self.deviceToken = deviceToken.map { String(format: "%02x", $0) }.joined()
    }

    /// Call with the tapped notification's payload. The server puts the card in `card_id`.
    func opened(userInfo: [AnyHashable: Any]) {
        openedCardID = userInfo["card_id"] as? Int
    }

    /// Sends the device token to the server. A failure is ignored: the app registers again on its next launch.
    func register(with client: APIClient) async {
        guard let deviceToken else { return }
        try? await client.registerDevice(token: deviceToken)
    }

    /// The card of the tapped push, once. Nil if no push was tapped or its card cannot be loaded.
    func takeOpenedCard(from client: APIClient) async -> Card? {
        guard let id = openedCardID else { return nil }
        openedCardID = nil
        return try? await client.card(id: id)
    }

    /// Asks the user for permission, then asks Apple for a device token, which arrives in `AppDelegate`.
    func requestPermission() async {
        let granted = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound])
        if granted == true {
            UIApplication.shared.registerForRemoteNotifications()
        }
    }
}

/// Receives what only UIKit delivers: the device token and taps on notifications.
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    let push = Push()

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // Set before launch finishes, so a tap that started the app is delivered too.
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        push.received(deviceToken: deviceToken)
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse) async {
        push.opened(userInfo: response.notification.request.content.userInfo)
    }
}
