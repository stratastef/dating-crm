import Foundation

/// The seven pipeline stages, in board order. Raw values match the server's `stage` field.
enum Stage: String, Codable, CaseIterable, Identifiable {
    case matched, chatting
    case numberSwapped = "number_swapped"
    case dateSet = "date_set"
    case dated
    case seeingThem = "seeing_them"
    case archived

    var id: Self { self }

    var title: String {
        switch self {
        case .matched: "Matched"
        case .chatting: "Chatting"
        case .numberSwapped: "Number swapped"
        case .dateSet: "Date set"
        case .dated: "Dated"
        case .seeingThem: "Seeing them"
        case .archived: "Archived"
        }
    }
}

/// Why autopilot is paused for one card. `pending`: a handover trigger hit and the user has not answered.
/// `takenOver`: the user keeps the chat manual until they hand it back.
enum Handover: String, Codable {
    case pending
    case takenOver = "taken_over"
}

struct Card: Codable, Identifiable, Hashable {
    let id: Int
    var app: String
    var name: String
    var stage: Stage
    var notes: String
    var nextAction: String?
    /// Local midnight of the due day; the server stores a plain date.
    var dueDate: Date?
    /// 1 to 5, nil until the user rates the date.
    var dateRating: Int?
    var dateNote: String?
    /// nil while autopilot may chat on this card.
    var handover: Handover?
    /// The replies suggested for the handover.
    var handoverSuggestions: [String]?

    // The card summary: what a row shows, sent with every card so the app makes no other call.
    var stageChangedAt: Date?
    /// No message from either side for the user's set number of days. A flag, not a stage.
    var stalled = false
    /// The newest message, from either side; nil when there are none.
    var lastMessage: LastMessage?
    /// A hot lead, as the review queue has it.
    var hot = false
    /// The draft waiting in Review; nil when there is none.
    var pendingDraft: Draft?
    /// nil when unknown: the row shows the monogram.
    var leadPhotoUrl: URL?

    /// True when the card is in Dated and has no rating yet: the app then asks for one.
    var needsDateRating: Bool { stage == .dated && dateRating == nil }

    /// The row's time: the last message, or the last stage change when there are no messages.
    var lastActivity: Date? { lastMessage?.sentAt ?? stageChangedAt }
}

/// A card's newest message, as its summary carries it. `body` is the first 100 characters.
struct LastMessage: Codable, Hashable {
    var sender: Message.Sender
    var body: String
    var sentAt: Date
}

struct Message: Codable, Identifiable, Hashable {
    enum Sender: String, Codable { case me, them }

    let id: Int
    var sender: Sender
    var body: String
    var sentAt: Date
}

/// Today: the review summary, then what the user has to do by day, in the time zone the app sent.
struct Today: Codable, Equatable {
    var review: ReviewSummary
    var overdue: [TodayItem]
    var today: [TodayItem]
    var comingUp: [TodayItem]

    /// Nothing in any of the three groups: "Nothing for today".
    var isEmpty: Bool { overdue.isEmpty && today.isEmpty && comingUp.isEmpty }
}

/// How many items wait in Review, and how many of them are hot leads.
struct ReviewSummary: Codable, Equatable {
    var count = 0
    var hot = 0
}

struct TodayItem: Codable, Identifiable, Hashable {
    enum Kind: String, Codable {
        case date
        case nextAction = "next_action"
        case stalled
        case rateDate = "rate_date"
    }

    var kind: Kind
    var card: Card
    /// `date`: when the confirmed date starts.
    var startsAt: Date?
    /// `nextAction`: local midnight of its due day.
    var dueDate: Date?
    /// Under Overdue: whole days past the due day.
    var daysLate: Int?

    var id: String { "\(kind.rawValue)-\(card.id)" }
}

/// One week on the dashboard. `week` is local midnight of the Monday it starts on.
struct DashboardWeek: Codable, Identifiable, Equatable {
    var week: Date
    var goodDates: Int
    var hours: Double
    /// nil when no time was recorded that week.
    var goodDatesPerHour: Double?

    var id: Date { week }
}

/// A message Claude wrote for a card. `original` is Claude's text; `edited` is the user's version of it.
struct Draft: Codable, Identifiable, Hashable {
    enum Kind: String, Codable { case opener, reply }

    let id: Int
    var kind: Kind
    var original: String
    var edited: String?

    /// What to show and copy: the user's edit when there is one.
    var text: String { edited ?? original }
}

/// One thing Claude inferred about a match. `value` is Claude's; `corrected` is the user's correction of it.
struct Inference: Codable, Identifiable, Hashable {
    let id: Int
    /// The server's name for what is inferred, for example `texting_style` or `tone`.
    var kind: String
    var value: String
    var evidence: String
    /// 0 to 1.
    var confidence: Double
    var corrected: String?

    /// What to show and use: the user's correction when there is one.
    var text: String { corrected ?? value }

    /// The kind as a label: `texting_style` reads "Texting style".
    var title: String {
        let words = kind.replacing("_", with: " ")
        return words.prefix(1).uppercased() + words.dropFirst()
    }
}

/// One thing that waits for the user's review. `kind` is `draft` or `handover`; the server adds more kinds later.
struct QueueItem: Codable, Identifiable, Hashable {
    var kind: String
    /// A hot lead: the server pushed it at once.
    var hot: Bool
    /// Nil when `kind` is `paid_item`: a profile to swipe on is not a card.
    var cardID: Int?
    var cardName: String
    /// Set when `kind` is `draft`.
    var draft: Draft?
    /// Set when `kind` is `handover`: the suggested replies.
    var suggestions: [String]?
    /// Set when `kind` is `paid_item`.
    var paidItem: PaidItem?

    var id: String { "\(kind)-\(draft?.id ?? paidItem?.id ?? cardID ?? 0)" }

    // The key strategy turns `card_id` into `cardId`.
    enum CodingKeys: String, CodingKey {
        case kind, hot, draft, suggestions, paidItem
        case cardID = "cardId"
        case cardName
    }
}

/// A Super Like, Rose or Boost the server proposes to spend. It is spent only when the user approves.
struct PaidItem: Codable, Identifiable, Hashable {
    let id: Int
    var app: String
    /// `super_like`, `rose` or `boost`.
    var item: String
    /// The profile the item is for; the app's name for a Boost.
    var name: String
    var reason: String
    /// `pending`, `declined`, `spent`, or `failed`: approved, but the dating app did not spend it.
    var status: String

    var title: String { "\(item.replacingOccurrences(of: "_", with: " ").capitalized) on \(app.capitalized)" }
}

enum Swipe: String, Codable {
    case like, pass

    var title: String { self == .like ? "Like" : "Pass" }
}

/// A profile a dating app offers to swipe on, with the server's suggestion. The user decides.
struct SwipeCandidate: Codable, Identifiable, Hashable {
    let id: Int
    var app: String
    var name: String
    var bio: String
    var photos: [URL]
    var suggestion: Swipe
    var reason: String
    /// Which pre-filter suggested: `jev` or `model`.
    var source: String
}

/// Pause: what autopilot is paused for. `all` pauses every app; `apps` are paused on their own.
struct Pauses: Codable, Equatable {
    var all = false
    var apps: [String] = []
}

/// How much the app may do alone for one job (`chat`, `profile`, `swipe`). Raw values match the server's.
enum AutonomyLevel: String, Codable, CaseIterable, Identifiable {
    case off, copilot, autopilot
    case fullAutopilot = "full_autopilot"

    var id: Self { self }
    var title: String { self == .fullAutopilot ? "Full autopilot" : rawValue.capitalized }

    /// What the level lets the app do, in plain words (GLOSSARY.md, Autonomy).
    var summary: String {
        switch self {
        case .off: "The app does nothing here unless you ask."
        case .copilot: "The app drafts and suggests. You decide and send."
        case .autopilot: "The app acts alone within your limits. Date plans and every handover come to you."
        case .fullAutopilot: "The app also plans and books dates alone. Handovers still come to you."
        }
    }
}

/// The AI budget of the current month, in USD. `paused`: the spend is at the cap, so autopilot is paused.
struct Budget: Codable, Equatable {
    var spendUsd: Double
    var capUsd: Double
    var paused: Bool

    /// "$8.20 of $30": cents only when there are any.
    var spentOfCap: String { "\(Self.dollars(spendUsd)) of \(Self.dollars(capUsd))" }

    private static func dollars(_ usd: Double) -> String {
        // en_US: "$30", not "US$30" outside the US. The app is not localized.
        usd.formatted(
            .currency(code: "USD").locale(Locale(identifier: "en_US"))
                .precision(.fractionLength(usd == usd.rounded() ? 0 : 2)))
    }
}

/// How many profiles swipe autopilot may swipe on, per app: per run of the job (1 to 10) and per day (1 to 100).
struct SwipeLimits: Codable, Equatable {
    var swipesPerRun: Int
    var swipesPerDay: Int
}

/// A purge cannot be undone, so the user types the word before the button works.
enum PurgeConfirmation {
    static let word = "purge"

    static func allows(typed: String, chosen: Int) -> Bool {
        chosen > 0 && typed.trimmingCharacters(in: .whitespaces).lowercased() == word
    }
}

/// What the user wants: wishes in plain words, plus must-haves and dealbreakers.
struct Preferences: Codable, Equatable {
    var wishes = ""
    var mustHaves: [String] = []
    var dealbreakers: [String] = []
}

/// The voice questionnaire: the server's questions and the user's answers, keyed by the question's text.
struct Voice: Decodable, Equatable {
    var questions: [String]
    var answers: [String: String]
}

/// One of the user's own photos on the server.
struct ProfilePhoto: Codable, Identifiable, Equatable {
    let id: Int
    /// 1 is the best photo. nil, like `reason`, until the photos are ranked.
    var rank: Int?
    var reason: String?
    /// The light edit on offer, to accept or reject. nil when there is none.
    var suggestedEdit: PhotoEdit?
    /// The edit the user accepted. nil while the photo is as uploaded.
    var edit: PhotoEdit?
}

/// A light edit the server applies to the uploaded pixels with ordinary image code. Nothing is generated.
struct PhotoEdit: Codable, Equatable {
    /// Left, top, right, bottom as fractions of the width and height. nil keeps the whole photo.
    var crop: [Double]?
    /// 1 changes nothing; below is darker, above brighter.
    var exposure: Double
    /// 1 changes nothing; below is less saturated, above more.
    var colour: Double

    /// The changes in words, for the offer: "crop, brighter".
    var summary: String {
        var parts: [String] = []
        if crop != nil { parts.append("crop") }
        if exposure != 1 { parts.append(exposure > 1 ? "brighter" : "darker") }
        if colour != 1 { parts.append(colour > 1 ? "more colour" : "less colour") }
        return parts.joined(separator: ", ")
    }
}
