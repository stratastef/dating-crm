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

/// One thing that waits for the user's review. `kind` is `draft` so far; the server adds more kinds later.
struct QueueItem: Codable, Identifiable, Hashable {
    var kind: String
    /// A hot lead: the server pushed it at once.
    var hot: Bool
    var cardID: Int
    var cardName: String
    /// Set when `kind` is `draft`.
    var draft: Draft?

    var id: String { "\(kind)-\(draft?.id ?? cardID)" }

    // The key strategy turns `card_id` into `cardId`.
    enum CodingKeys: String, CodingKey {
        case kind, hot, draft
        case cardID = "cardId"
        case cardName
    }
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

/// What the user wants: wishes in plain words, plus must-haves and dealbreakers.
struct Preferences: Codable, Equatable {
    var wishes = ""
    var mustHaves: [String] = []
    var dealbreakers: [String] = []
}
