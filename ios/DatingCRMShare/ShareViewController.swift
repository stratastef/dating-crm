import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// What the share sheet opens for "Dating CRM": sends the shared screenshot to the server and shows the draft.
final class ShareViewController: UIViewController {
    private let model = ScreenshotImport()

    override func viewDidLoad() {
        super.viewDidLoad()
        let host = UIHostingController(rootView: ScreenshotImportView(model: model) { [weak self] in
            self?.extensionContext?.completeRequest(returningItems: nil)
        })
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
        // `Session()` reads the server URL and token the app stored when the user signed in.
        Task { await model.run(client: Session().client, image: await sharedImage()) }
    }

    /// The first picture among the shared items, as the bytes its owner hands over.
    private func sharedImage() async -> Data? {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        let image = UTType.image.identifier
        guard let provider = items.flatMap({ $0.attachments ?? [] }).first(where: { $0.hasItemConformingToTypeIdentifier(image) })
        else { return nil }
        return await withCheckedContinuation { continuation in
            _ = provider.loadDataRepresentation(forTypeIdentifier: image) { data, _ in continuation.resume(returning: data) }
        }
    }
}
