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

    /// True when the card is in Dated and has no rating yet: the app then asks for one.
    var needsDateRating: Bool { stage == .dated && dateRating == nil }
}

struct Message: Codable, Identifiable, Hashable {
    enum Sender: String, Codable { case me, them }

    let id: Int
    var sender: Sender
    var body: String
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
    var cardID: Int
    var cardName: String
    /// Set when `kind` is `draft`.
    var draft: Draft?
    /// Set when `kind` is `handover`: the suggested replies.
    var suggestions: [String]?

    var id: String { "\(kind)-\(draft?.id ?? cardID)" }

    // The key strategy turns `card_id` into `cardId`.
    enum CodingKeys: String, CodingKey {
        case kind, hot, draft, suggestions
        case cardID = "cardId"
        case cardName
    }
}

/// What the user wants: wishes in plain words, plus must-haves and dealbreakers.
struct Preferences: Codable, Equatable {
    var wishes = ""
    var mustHaves: [String] = []
    var dealbreakers: [String] = []
}
