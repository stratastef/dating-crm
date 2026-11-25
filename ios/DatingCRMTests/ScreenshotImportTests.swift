import Foundation
import Testing
import UIKit
@testable import DatingCRM

struct ScreenshotImportTests {
    let server = StubServer()
    let draftJSON = #"{"id": 5, "card_id": 1, "kind": "reply", "status": "pending", "original": "both. badly.", "edited": null}"#

    /// A real picture, as the share sheet hands one over.
    private var png: Data {
        UIGraphicsImageRenderer(size: CGSize(width: 4, height: 4)).pngData { $0.fill(CGRect(x: 0, y: 0, width: 4, height: 4)) }
    }

    @Test func uploadsTheScreenshotAsJPEGAndShowsTheDraftTheServerReturns() async throws {
        server.respond(draftJSON, status: 201)
        let model = ScreenshotImport()
        #expect(model.state == .reading)

        await model.run(client: server.client(), image: png)

        #expect(model.state == .draft(Draft(id: 5, kind: .reply, original: "both. badly.", edited: nil)))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/screenshots")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer secret")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "image/jpeg")
        #expect(request.httpBody?.prefix(3) == Data([0xFF, 0xD8, 0xFF]))  // the JPEG signature
    }

    @Test func asksTheUserToSignInWhenTheAppHasNoSession() async {
        let model = ScreenshotImport()

        await model.run(client: nil, image: png)

        #expect(model.state == .failed("Open Dating CRM and sign in first."))
        #expect(server.requests.isEmpty)
    }

    @Test func refusesSomethingThatIsNotAPicture() async {
        let model = ScreenshotImport()

        await model.run(client: server.client(), image: Data("not a picture".utf8))
        #expect(model.state == .failed("This is not a picture Dating CRM can read."))

        await model.run(client: server.client(), image: nil)
        #expect(model.state == .failed("This is not a picture Dating CRM can read."))
        #expect(server.requests.isEmpty)
    }

    @Test func showsWhyTheServerCouldNotWriteADraft() async {
        let model = ScreenshotImport()

        server.respond(#"{"detail": "style profile not written yet"}"#, status: 409)
        await model.run(client: server.client(), image: png)
        #expect(model.state == .failed("The server has no style profile for you yet, so it cannot write a draft."))

        server.respond(#"{"detail": "the screenshot could not be read, try again"}"#, status: 502)
        await model.run(client: server.client(), image: png)
        #expect(model.state == .failed("The screenshot could not be read. Share it again."))

        server.respond(#"{"detail": "invalid or missing token"}"#, status: 401)
        await model.run(client: server.client(), image: png)
        #expect(model.state == .failed("The server rejected the API token."))
    }
}
