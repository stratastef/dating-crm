import Foundation
import Testing
@testable import DatingCRM

struct PhotosTests {
    let server = StubServer()

    @Test func uploadsThePhotoFileItselfAsJPEG() async throws {
        server.respond(#"{"id": 7, "rank": null, "reason": null, "suggested_edit": null, "edit": null}"#, status: 201)
        let jpeg = Data([0xFF, 0xD8, 0xFF, 0xD9])

        let photo = try await server.client().uploadPhoto(jpeg: jpeg)

        #expect(photo == ProfilePhoto(id: 7))
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/photos")
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "image/jpeg")
        #expect(request.httpBody == jpeg)
    }

    @Test func rankingReturnsThePhotosBestFirstWithAReasonAndTheEditOnOffer() async throws {
        server.respond("""
        [{"id": 9, "rank": 1, "reason": "Clear face.", "suggested_edit": null, "edit": null},
         {"id": 7, "rank": 2, "reason": "Too dark.",
          "suggested_edit": {"crop": [0, 0, 0.5, 1], "exposure": 1.2, "colour": 1}, "edit": null}]
        """)

        let photos = try await server.client().rankPhotos()

        #expect(photos == [
            ProfilePhoto(id: 9, rank: 1, reason: "Clear face."),
            ProfilePhoto(
                id: 7, rank: 2, reason: "Too dark.",
                suggestedEdit: PhotoEdit(crop: [0, 0, 0.5, 1], exposure: 1.2, colour: 1)
            ),
        ])
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://crm.test/photos/rank")
    }

    @Test func listsThePhotos() async throws {
        server.respond("[]")

        #expect(try await server.client().photos().isEmpty)
        #expect(server.requests.first?.httpMethod == "GET")
        #expect(server.requests.first?.url?.absoluteString == "https://crm.test/photos")
    }

    @Test func readsThePhotoAndThePreviewOfItsEditAsImageData() async throws {
        server.respond("image")
        server.respond("preview")
        let client = server.client()

        #expect(try await client.photoImage(id: 7) == Data("image".utf8))
        #expect(try await client.photoPreview(id: 7) == Data("preview".utf8))
        #expect(server.requests.map(\.url?.absoluteString) == [
            "https://crm.test/photos/7/image", "https://crm.test/photos/7/preview",
        ])
    }

    @Test(arguments: [true, false])
    func acceptsOrRejectsTheEditOnOffer(accept: Bool) async throws {
        server.respond(#"{"id": 7, "rank": 2, "reason": "Too dark.", "suggested_edit": null, "edit": null}"#)

        let photo = try await server.client().decideEdit(photoID: 7, accept: accept)

        #expect(photo.suggestedEdit == nil)
        let request = try #require(server.requests.first)
        #expect(request.httpMethod == "PUT")
        #expect(request.url?.absoluteString == "https://crm.test/photos/7/edit")
        let body = try #require(request.httpBody)
        #expect(try JSONSerialization.jsonObject(with: body) as? NSDictionary == ["accept": accept] as NSDictionary)
    }
}
