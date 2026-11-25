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
        _ = try await data("POST", "time", body: Self.encoder.encode(["seconds": seconds]))
    }

    private func send<Response: Decodable>(_ method: String, _ path: String, body: Data? = nil) async throws -> Response {
        try Self.decoder.decode(Response.self, from: await data(method, path, body: body))
    }

    private func data(_ method: String, _ path: String, body: Data? = nil) async throws -> Data {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = method
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
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
