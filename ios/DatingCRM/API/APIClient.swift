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

    // Sign-in. The first two need no token: call them on a client whose token is "".

    /// Texts a sign-in code to the phone number (E.164). `403` means no account has the number, and the invite code
    /// was missing, unknown or used. `429` means too many codes were asked for.
    func requestSignInCode(phone: String, inviteCode: String? = nil) async throws {
        var body = ["phone": phone]
        body["invite_code"] = inviteCode
        try await data("POST", "sign-in/code", body: Self.encoder.encode(body))
    }

    /// Trades the phone number and sign-in code for an API token for this device. `401` means a wrong code,
    /// `410` an expired one, `429` too many tries, `403` an invite code that created another account meanwhile.
    func signIn(phone: String, code: String) async throws -> SignedIn {
        try await send("POST", "sign-in", body: Self.encoder.encode(["phone": phone, "code": code]))
    }

    /// Revokes this device's token. The server stops sending this phone the user's pushes.
    func signOut() async throws {
        try await data("POST", "sign-out")
    }

    /// The review summary and what the user has to do: Overdue, Today and Coming up.
    func today() async throws -> Today {
        try await send("GET", "today")
    }

    /// Stores the phone's time zone (an IANA name), which "today" and "overdue" follow. Sent on each launch.
    func setTimeZone(_ identifier: String) async throws {
        try await data("PATCH", "settings", body: Self.encoder.encode(["time_zone": identifier]))
    }

    /// Each setup step, in order, and whether it is done.
    func setup() async throws -> [SetupStep] {
        try await send("GET", "setup")
    }

    /// Hides "Finish setup" on Today, or shows it again. The steps stay under You either way.
    func setSetupDismissed(_ dismissed: Bool) async throws {
        try await data("PATCH", "settings", body: Self.encoder.encode(["setup_dismissed": dismissed]))
    }

    func cards() async throws -> [Card] {
        try await send("GET", "cards")
    }

    /// Every card, grouped by who acts next. Empty groups are left out.
    func pipeline() async throws -> [PipelineGroup] {
        try await send("GET", "pipeline")
    }

    /// Adds a card by hand, for a match on an app without a connector.
    func addCard(name: String, app: String, stage: Stage) async throws -> Card {
        try await send("POST", "cards", body: Self.encoder.encode(["name": name, "app": app, "stage": stage.rawValue]))
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

    /// Send, or Retry a failed send: the server holds the draft 5 seconds for Undo, then its worker sends it
    /// through the dating app. `409` means the server refused: sending is off for the app, the draft denies being
    /// AI, or it was already sent. A pause does not stop it.
    /// Send at: with `at`, the worker sends it then, as given and with no Undo wait; `unschedule` takes it back.
    func sendDraft(draftID: Int, at: Date? = nil) async throws {
        let body = try at.map { try Self.encoder.encode(["send_at": $0.ISO8601Format()]) }
        try await data("POST", "drafts/\(draftID)/send", body: body)
    }

    /// Undo of a Send the server still holds: the draft is pending again, with its edit. `409` means the worker
    /// already started sending it.
    func undoSend(draftID: Int) async throws -> Draft {
        try await send("POST", "drafts/\(draftID)/undo-send")
    }

    /// Cancel of a scheduled send (Send at): the draft is pending again, with its edit. `409` means it is going out.
    func unschedule(draftID: Int) async throws -> Draft {
        try await send("POST", "drafts/\(draftID)/unschedule")
    }

    /// Everything that waits for the user's review, hot leads first.
    func queue() async throws -> [QueueItem] {
        try await send("GET", "queue")
    }

    /// Copy: the user took a pending or failed draft's text to send by hand. It waits in Review as
    /// `copied_draft` until the user's message shows up in the chat. Save an edit first.
    func copy(draftID: Int) async throws -> Draft {
        try await send("POST", "drafts/\(draftID)/copy")
    }

    /// Drops a pending draft from the queue, or clears a copied or failed one. Nothing is sent.
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

    /// The voice questionnaire's questions, as the server words them, and the user's answers.
    func voice() async throws -> Voice {
        try await send("GET", "voice")
    }

    /// Replaces all the questionnaire answers. The server then rewrites the style profile.
    func saveAnswers(_ answers: [String: String]) async throws -> Voice {
        try await send("PUT", "voice/questionnaire", body: Self.encoder.encode(["answers": answers]))
    }

    /// Good dates per hour for every week with recorded time or a good date, oldest first, with the headline,
    /// this month's funnel and AI spend.
    func dashboard() async throws -> Dashboard {
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

    /// The Swipe layout the user chose. Nil until they choose: Swipe shows one at a time meanwhile.
    func swipeLayout() async throws -> SwipeLayout? {
        let setting: LayoutSetting = try await send("GET", "swipes/layout")
        return setting.layout
    }

    func setSwipeLayout(_ layout: SwipeLayout) async throws -> SwipeLayout? {
        let setting: LayoutSetting = try await send(
            "PUT", "swipes/layout", body: Self.encoder.encode(LayoutSetting(layout: layout)))
        return setting.layout
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

    /// Deletes the photo and its file on the server. It cannot be undone.
    func deletePhoto(id: Int) async throws {
        try await data("DELETE", "photos/\(id)")
    }

    /// Sets the photos' order, lead photo first. `ids` names every photo once. Returns the photos in that order.
    func orderPhotos(ids: [Int]) async throws -> [ProfilePhoto] {
        try await send("PUT", "photos/order", body: Self.encoder.encode(["ids": ids]))
    }

    /// The bio and prompt answers the user accepted for a dating app (`tinder`); empty until they accept one.
    func bio(app: String) async throws -> Bio {
        try await send("GET", "bios/\(app)")
    }

    /// Has Claude rewrite the bio and prompt answers for the app in the user's voice. Stores nothing. `409`: the
    /// style profile is not written yet, so the voice questionnaire comes first.
    func rewriteBio(app: String, _ current: Bio) async throws -> Bio {
        try await send("POST", "bios/\(app)/rewrite", body: Self.encoder.encode(current))
    }

    /// Stores the version the user accepted for the app, replacing the previous one.
    func acceptBio(app: String, _ accepted: Bio) async throws -> Bio {
        try await send("PUT", "bios/\(app)", body: Self.encoder.encode(accepted))
    }

    /// What stops autopilot now, for the status strip: pauses, the AI budget, broken connectors. Empty when nothing does.
    func status() async throws -> [StatusMessage] {
        try await send("GET", "status")
    }

    // Settings. Each call returns the state the server now holds.

    /// What is paused.
    func pauses() async throws -> Pauses {
        try await send("GET", "autopilot/pause")
    }

    /// Pauses or resumes autopilot for one app, or for all apps when `app` is nil. A pause stops only what
    /// the server would do alone: a draft the user taps still sends.
    func setPaused(_ paused: Bool, app: String? = nil) async throws -> Pauses {
        try await send("POST", "autopilot/\(paused ? "pause" : "resume")", query: app.map { ["app": $0] } ?? [:])
    }

    /// The autonomy level of each job: `chat`, `profile`, `swipe`.
    func autonomy() async throws -> [String: AutonomyLevel] {
        try await send("GET", "autonomy")
    }

    func setAutonomy(job: String, level: AutonomyLevel) async throws -> [String: AutonomyLevel] {
        try await send("PUT", "autonomy/\(job)", body: Self.encoder.encode(["level": level]))
    }

    /// This month's AI spend and the cap.
    func budget() async throws -> Budget {
        try await send("GET", "budget")
    }

    func setBudgetCap(_ usd: Double) async throws -> Budget {
        try await send("PUT", "budget", body: Self.encoder.encode(["cap_usd": usd]))
    }

    /// How many profiles swipe autopilot may swipe on, per run and per day.
    func swipeLimits() async throws -> SwipeLimits {
        try await send("GET", "swipes/limits")
    }

    func setSwipeLimits(_ limits: SwipeLimits) async throws -> SwipeLimits {
        try await send("PUT", "swipes/limits", body: Self.encoder.encode(limits))
    }

    // Connected apps.

    /// Each dating app (Tinder, Hinge, Bumble) with its connector state.
    func connectedApps() async throws -> [ConnectedApp] {
        try await send("GET", "connectors")
    }

    /// Stores the app's session token on the server, which turns its connector on and syncs now. `404`: the
    /// app has no connector.
    func connect(app: String, token: String) async throws {
        try await data("PUT", "connectors/\(app)/token", body: Self.encoder.encode(["token": token]))
    }

    /// Keeps the app copilot-only: the server deletes its session token and stops syncing, sending and
    /// swiping there. `connect` turns it back on.
    func chooseCopilotOnly(app: String) async throws {
        try await data("PUT", "connectors/\(app)/copilot-only")
    }

    // Google Calendar.

    /// Whether the server holds a Google Calendar refresh token, so offered time slots get holds.
    func calendarConnected() async throws -> Bool {
        let calendar: [String: Bool] = try await send("GET", "calendar")
        return calendar["connected"] ?? false
    }

    /// Google's consent page, to open in a web authentication session. Google returns to the server, which sends
    /// the session on to `datingcrm://calendar`. `503`: the server has no Google OAuth client set up.
    func calendarConsentURL() async throws -> URL {
        let consent: Consent = try await send("GET", "calendar/connect")
        return consent.url
    }

    /// Whether the match read may guess ethnicity, religion, health, sexuality and politics. Off by default.
    func protectedTraitGuesses() async throws -> Bool {
        try await enabled("GET", "settings/protected-trait-guesses")
    }

    func setProtectedTraitGuesses(_ on: Bool) async throws {
        _ = try await enabled("PUT", "settings/protected-trait-guesses", on)
    }

    /// Whether the first message sent alone to a match says that an AI helps write. On by default.
    func aiDisclosure() async throws -> Bool {
        try await enabled("GET", "settings/ai-disclosure")
    }

    func setAIDisclosure(_ on: Bool) async throws {
        _ = try await enabled("PUT", "settings/ai-disclosure", on)
    }

    /// Push name previews, Blur photos and the night window.
    func settings() async throws -> UserSettings {
        try await send("GET", "settings")
    }

    /// The hours autopilot sends nothing, 0 to 23 in the user's time zone. 1 to 7 by default.
    func setNightWindow(start: Int, end: Int) async throws -> UserSettings {
        try await send("PATCH", "settings", body: Self.encoder.encode(["night_window_start": start, "night_window_end": end]))
    }

    /// Lets hot-lead and handover pushes name the match. Off by default.
    func setPushNamePreviews(_ on: Bool) async throws -> UserSettings {
        try await send("PATCH", "settings", body: Self.encoder.encode(["push_name_previews": on]))
    }

    /// Blurs faces until tapped. Off by default.
    func setBlurPhotos(_ on: Bool) async throws -> UserSettings {
        try await send("PATCH", "settings", body: Self.encoder.encode(["blur_photos": on]))
    }

    /// What the app did toward dating apps and the calendar, newest first.
    func activityLog() async throws -> [ActivityEntry] {
        try await send("GET", "audit-log")
    }

    /// The user's cards, on every app, whose name or handle contains `query`.
    func findPeople(_ query: String) async throws -> [Card] {
        try await send("GET", "people", query: ["q": query])
    }

    /// The profiles the user only swiped on whose name or profile ID contains `query`.
    func findCandidates(_ query: String) async throws -> [SwipeCandidate] {
        try await send("GET", "people/candidates", query: ["q": query])
    }

    /// Deletes the cards and swipe candidates and everything stored about them. It cannot be undone.
    /// Returns how many were deleted.
    func purge(cardIDs: [Int], candidateIDs: [Int]) async throws -> Int {
        let purged: Purged = try await send(
            "POST", "people/purge",
            body: Self.encoder.encode(Purge(cardIds: cardIDs, candidateIds: candidateIDs, confirm: PurgeConfirmation.word)))
        return purged.purged
    }

    private func enabled(_ method: String, _ path: String, _ on: Bool? = nil) async throws -> Bool {
        let body = try on.map { try Self.encoder.encode(["enabled": $0]) }
        let setting: [String: Bool] = try await send(method, path, body: body)
        return setting["enabled"] ?? false
    }

    private func send<Response: Decodable>(
        _ method: String, _ path: String, body: Data? = nil, query: [String: String] = [:]
    ) async throws -> Response {
        try Self.decoder.decode(Response.self, from: await data(method, path, body: body, query: query))
    }

    /// For routes that answer with no body, call this instead of `send`.
    @discardableResult
    private func data(
        _ method: String, _ path: String, body: Data? = nil, contentType: String = "application/json",
        query: [String: String] = [:]
    ) async throws -> Data {
        var url = baseURL.appending(path: path)
        if !query.isEmpty {
            url.append(queryItems: query.map { URLQueryItem(name: $0.key, value: $0.value) })
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !token.isEmpty { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.httpBody = body
            request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        }
        let (data, response) = try await transport(request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else { throw APIError(status: status) }
        return data
    }

    // Plain days such as `due_date`. The app writes only these; it reads timestamps too.
    // `nonisolated`: the decoder's date closure is Sendable.
    nonisolated private static let dayFormat: DateFormatter = {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.dateFormat = "yyyy-MM-dd"
        return format
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // A plain day (`2026-12-01`) or a full timestamp, with or without fractional seconds.
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            if let date = dayFormat.date(from: text)
                ?? (try? Date(text, strategy: .iso8601.time(includingFractionalSeconds: true)))
                ?? (try? Date(text, strategy: .iso8601)) {
                return date
            }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Not a date: \(text)"))
        }
        return decoder
    }()

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .formatted(dayFormat)
        return encoder
    }()
}

struct SignedIn: Decodable {
    let token: String
    /// True when this sign-in created the account (with an invite code).
    let newAccount: Bool
}

private struct Consent: Decodable {
    let url: URL
}

private struct SwipeDecided: Decodable {
    let applied: Bool
}

private struct LayoutSetting: Codable {
    let layout: SwipeLayout?
}

private struct Purge: Encodable {
    let cardIds: [Int]
    let candidateIds: [Int]
    let confirm: String
}

private struct Purged: Decodable {
    let purged: Int
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
