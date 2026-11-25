import Foundation

/// A non-2xx answer from the server.
struct APIError: LocalizedError, Equatable {
    let status: Int

    var errorDescription: String? {
        status == 401 ? "The server rejected the API token." : "The server answered with status \(status)."
    }
}

/// Every call to the server goes through this type. Add one method per route.
/// Tests replace `transport` to stand in for the server.
struct APIClient {
    typealias Transport = @Sendable (URLRequest) async throws -> (Data, URLResponse)

    var baseURL: URL
    var token: String
    var transport: Transport = { try await URLSession.shared.data(for: $0) }

    func cards() async throws -> [Card] {
        try await send("GET", "cards")
    }

    func messages(cardID: Int) async throws -> [Message] {
        try await send("GET", "cards/\(cardID)/messages")
    }

    /// Saves the card's stage, notes, next action, due date, date rating and date note, and returns the stored card.
    func update(_ card: Card) async throws -> Card {
        try await send("PATCH", "cards/\(card.id)", body: Self.encoder.encode(CardChanges(card: card)))
    }

    /// Has Claude write a draft for the card: an opener when it has no messages, a reply otherwise.
    func writeDraft(cardID: Int) async throws -> Draft {
        try await send("POST", "cards/\(cardID)/drafts")
    }

    /// Stores the user's version of a draft. The server keeps Claude's original next to it.
    func saveEdit(draftID: Int, text: String) async throws -> Draft {
        try await send("PATCH", "drafts/\(draftID)", body: Self.encoder.encode(["edited": text]))
    }

    /// Has the server read a screenshot of a chat or profile into the match's card, and returns a draft for it.
    func importScreenshot(jpeg: Data) async throws -> Draft {
        try Self.decoder.decode(Draft.self, from: await data("POST", "screenshots", body: jpeg, contentType: "image/jpeg"))
    }

    /// The match read of a card: empty until one is made.
    func read(cardID: Int) async throws -> [Inference] {
        try await send("GET", "cards/\(cardID)/read")
    }

    /// Has Claude read the match again. Corrections are kept.
    func makeRead(cardID: Int) async throws -> [Inference] {
        try await send("POST", "cards/\(cardID)/read")
    }

    /// Stores the user's correction of an inference. The server keeps Claude's value next to it.
    func correct(inferenceID: Int, text: String) async throws -> Inference {
        try await send("PATCH", "inferences/\(inferenceID)", body: Self.encoder.encode(["corrected": text]))
    }

    /// Approves a draft: the server queues it and its worker sends it through the dating app. `409` means the
    /// server refused: the app is paused, sending is off for it, or the draft was already sent.
    func sendDraft(draftID: Int) async throws {
        try await data("POST", "drafts/\(draftID)/send")
    }

    /// Everything that waits for the user's review, hot leads first.
    func queue() async throws -> [QueueItem] {
        try await send("GET", "queue")
    }

    /// Approves a pending draft as the server holds it. Save an edit first.
    func approve(draftID: Int) async throws {
        try await data("POST", "drafts/\(draftID)/approve")
    }

    /// Drops a pending draft from the queue. Nothing is sent.
    func dismiss(draftID: Int) async throws {
        try await data("POST", "drafts/\(draftID)/dismiss")
    }

    /// Approves a proposed paid item: the server spends it now. `status` of the answer is `spent` or `failed`.
    func approve(paidItemID: Int) async throws -> PaidItem {
        try await send("POST", "paid-items/\(paidItemID)/approve")
    }

    /// Declines a proposed paid item. Nothing is spent.
    func decline(paidItemID: Int) async throws {
        try await data("POST", "paid-items/\(paidItemID)/decline")
    }

    /// Keeps the card's chat manual: autopilot stays out until `handBack`.
    func takeOver(cardID: Int) async throws {
        try await data("POST", "cards/\(cardID)/take-over")
    }

    /// Ends the card's handover pause: autopilot may chat on it again.
    func handBack(cardID: Int) async throws {
        try await data("POST", "cards/\(cardID)/hand-back")
    }

    func card(id: Int) async throws -> Card {
        try await send("GET", "cards/\(id)")
    }

    /// Tells the server where to send this phone's push notifications. `token` is the APNs device token in hex.
    func registerDevice(token: String) async throws {
        try await data("POST", "devices", body: Self.encoder.encode(["token": token]))
    }

    /// The preferences in force; empty until the user saves some.
    func preferences() async throws -> Preferences {
        try await send("GET", "preferences")
    }

    /// Stores the preferences as a new version on the server and returns what it stored.
    func save(_ preferences: Preferences) async throws -> Preferences {
        try await send("PUT", "preferences", body: Self.encoder.encode(preferences))
    }

    /// Good dates per hour for every week with recorded time or a good date, oldest first.
    func dashboard() async throws -> [DashboardWeek] {
        try await send("GET", "dashboard")
    }

    /// Reports a stretch of time the user spent in the app.
    func recordTime(seconds: Int) async throws {
        try await data("POST", "time", body: Self.encoder.encode(["seconds": seconds]))
    }

    /// The profiles that wait for the user's swipe, each with the server's suggestion.
    func swipes() async throws -> [SwipeCandidate] {
        try await send("GET", "swipes")
    }

    /// Has the server read the app's next profiles and suggest like or pass for each. Returns all that wait.
    func suggestSwipes(app: String) async throws -> [SwipeCandidate] {
        try await send("POST", "swipes/\(app)/suggestions")
    }

    /// Stores the user's swipe and swipes in the dating app. False when the app was not reached:
    /// the swipe is stored and the user swipes there by hand.
    func swipe(candidateID: Int, _ swipe: Swipe) async throws -> Bool {
        let decided: SwipeDecided = try await send(
            "POST", "swipes/\(candidateID)/decision", body: Self.encoder.encode(["decision": swipe]))
        return decided.applied
    }

    /// The user's own photos, best first once ranked.
    func photos() async throws -> [ProfilePhoto] {
        try await send("GET", "photos")
    }

    /// Stores one of the user's photos on the server. `jpeg` is the JPEG file itself.
    func uploadPhoto(jpeg: Data) async throws -> ProfilePhoto {
        try Self.decoder.decode(ProfilePhoto.self, from: await data("POST", "photos", body: jpeg, contentType: "image/jpeg"))
    }

    /// Has Claude rank all the photos. Each comes back with a rank, a reason and perhaps a light edit on offer.
    func rankPhotos() async throws -> [ProfilePhoto] {
        try await send("POST", "photos/rank")
    }

    /// The photo's image file, with the accepted edit applied if there is one.
    func photoImage(id: Int) async throws -> Data {
        try await data("GET", "photos/\(id)/image")
    }

    /// The photo as it would look with the edit on offer. The server makes it from the uploaded pixels.
    func photoPreview(id: Int) async throws -> Data {
        try await data("GET", "photos/\(id)/preview")
    }

    /// Accepts or rejects the edit on offer for a photo. Either way the offer is gone afterwards.
    func decideEdit(photoID: Int, accept: Bool) async throws -> ProfilePhoto {
        try await send("PUT", "photos/\(photoID)/edit", body: Self.encoder.encode(["accept": accept]))
    }

    private func send<Response: Decodable>(_ method: String, _ path: String, body: Data? = nil) async throws -> Response {
        try Self.decoder.decode(Response.self, from: await data(method, path, body: body))
    }

    /// For routes that answer with no body, call this instead of `send`.
    @discardableResult
    private func data(
        _ method: String, _ path: String, body: Data? = nil, contentType: String = "application/json"
    ) async throws -> Data {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await transport(request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw APIError(status: status) }
        return data
    }

    // The only dates the app reads or writes are plain days such as `due_date`.
    private static let dayFormat: DateFormatter = {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.dateFormat = "yyyy-MM-dd"
        return format
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .formatted(dayFormat)
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .formatted(dayFormat)
        return encoder
    }()
}

private struct SwipeDecided: Decodable {
    let applied: Bool
}

private struct CardChanges: Encodable {
    let card: Card

    enum CodingKeys: CodingKey { case stage, notes, nextAction, dueDate, dateRating, dateNote }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(card.stage, forKey: .stage)
        try container.encode(card.notes, forKey: .notes)
        // `encode`, not `encodeIfPresent`: the server clears these two only on an explicit null.
        try container.encode(card.nextAction, forKey: .nextAction)
        try container.encode(card.dueDate, forKey: .dueDate)
        // The app never clears a rating or its note, so these are sent only when set.
        try container.encodeIfPresent(card.dateRating, forKey: .dateRating)
        try container.encodeIfPresent(card.dateNote, forKey: .dateNote)
    }
}
