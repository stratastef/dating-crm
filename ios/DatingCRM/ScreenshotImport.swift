import Observation
import UIKit

/// One screenshot shared from the share sheet: uploads it and holds what the share extension shows.
/// It is in the app's folder so the unit tests reach it; the share extension compiles it too.
@Observable final class ScreenshotImport {
    enum State: Equatable {
        case reading
        case draft(Draft)
        case failed(String)
    }

    private(set) var state = State.reading

    /// `client` is nil when nobody is signed in. `image` is the shared picture in any format UIKit reads.
    func run(client: APIClient?, image: Data?) async {
        state = .reading
        guard let client else { return state = .failed("Open Dating CRM and sign in first.") }
        // JPEG keeps a full-size screenshot well under the server's 5 MB limit; a PNG of one can be larger.
        guard let jpeg = image.flatMap(UIImage.init(data:))?.jpegData(compressionQuality: 0.8) else {
            return state = .failed("This is not a picture Dating CRM can read.")
        }
        do {
            state = .draft(try await client.importScreenshot(jpeg: jpeg))
        } catch let error as APIError where error.status == 409 {
            state = .failed("The server has no style profile for you yet, so it cannot write a draft.")
        } catch let error as APIError where error.status == 502 {
            state = .failed("The screenshot could not be read. Share it again.")
        } catch {
            state = .failed(error.localizedDescription)
        }
    }
}
