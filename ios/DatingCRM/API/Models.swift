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

    /// Matched and Chatting: the chat is in the dating app, so the card opens on Chat and offers Write draft.
    /// From Number swapped on, the user texts off the app and the card opens on Details.
    var chatsInApp: Bool { self == .matched || self == .chatting }

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
    /// When the card was made: when the match synced, or when the user added it.
    var createdAt: Date?
    /// No message from either side for the user's set number of days. A flag, not a stage.
    var stalled = false
    /// The newest message, from either side; nil when there are none.
    var lastMessage: LastMessage?
    /// A hot lead, as the review queue has it.
    var hot = false
    /// The draft waiting in Review; nil when there is none.
    var pendingDraft: Draft?
    /// The card's draft list: its pending, copied and failed drafts, newest first. The card docks the first.
    var drafts: [Draft]?
    /// Autopilot's planned send: the draft it sends alone at its `sendAt`, with its `timingReason`.
    var plannedSend: Draft?
    /// nil when unknown: the row shows the monogram.
    var leadPhotoUrl: URL?

    // Where the Pipeline lists the card, and why: the server's codes, worded by `pipelineStatus`.
    /// `waiting_for_you`, `handled_by_autopilot`, `waiting_for_them`, `texting_off_app` or `archived`.
    var pipelineGroup: String?
    /// Why the card is Waiting for you, such as `draft_in_review`; nil in the other groups.
    var reason: String?
    /// With reason `handover`: the check that hit, such as `logistics`.
    var handoverTrigger: String?
    /// When the card is Handled by autopilot: `writing_opener`, `drafting_reply`, `planned` or `sent_waiting`.
    var autopilotActivity: String?
    /// What the chat is about in a few words, such as "museums"; empty until the card's first draft.
    var topic: String?

    /// True when the card is in Dated and has no rating yet: the app then asks for one.
    var needsDateRating: Bool { stage == .dated && dateRating == nil }

    /// The row's time: the last message, or the last stage change when there are no messages.
    var lastActivity: Date? { lastMessage?.sentAt ?? stageChangedAt }
}

/// One Pipeline group from `GET /pipeline`, its cards in the server's order: hot leads, then the latest activity.
struct PipelineGroup: Codable, Identifiable, Hashable {
    var group: String
    var cards: [Card]

    var id: String { group }

    var title: String {
        switch group {
        case "waiting_for_you": "Waiting for you"
        case "handled_by_autopilot": "Handled by autopilot"
        case "waiting_for_them": "Waiting for them"
        case "texting_off_app": "Texting off-app"
        case "archived": "Archived"
        default: group
        }
    }
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
    /// The handover checks a message from the match hit, such as `logistics`; nil when it was not checked.
    var handover: [String]? = nil
    /// Autopilot sent it alone: the chat marks it. False for the user's own messages, sent drafts included.
    var sentByAutopilot = false
}

/// Today: the review summary, then what the user has to do by day, in the time zone the app sent.
struct Today: Codable, Equatable {
    var review: ReviewSummary
    /// "Finish setup": nil once the user dismissed it or no step is left.
    var setup: SetupSummary?
    var overdue: [TodayItem]
    var today: [TodayItem]
    var comingUp: [TodayItem]

    /// Nothing in any of the three groups: "Nothing for today".
    var isEmpty: Bool { overdue.isEmpty && today.isEmpty && comingUp.isEmpty }
}

/// How many setup steps are not done yet, for Today's "Finish setup" row.
struct SetupSummary: Codable, Equatable {
    var stepsLeft: Int
}

/// One setup step, in the order setup runs them, and whether it is done.
struct SetupStep: Codable, Equatable {
    enum Step: String, Codable {
        case datingApps = "dating_apps"
        case calendar, voice, preferences
        case swipeLayoutAndAutonomy = "swipe_layout_and_autonomy"
    }

    var step: Step
    var done: Bool
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

/// The Dashboard: the weeks, the headline (good dates per hour this week against the four-week average), this
/// month's funnel and this month's AI spend.
struct Dashboard: Codable, Equatable {
    var weeks: [DashboardWeek]
    /// Good dates per hour this week; nil with no time recorded this week.
    var thisWeek: Double?
    /// Good dates per hour over the four weeks before this one; nil with no time recorded in them.
    var fourWeekAverage: Double?
    var funnel: Funnel
    /// This month's AI spend over this month's good dates; nil with no good date this month.
    var spendPerGoodDateUsd: Double?
    /// This month's AI spend against the cap.
    var budget: Budget

    /// Cards that reached each stage this month. `good` counts good dates rated this month.
    struct Funnel: Codable, Equatable {
        var matched: Int
        var chatting: Int
        var dateSet: Int
        var dated: Int
        var good: Int
    }
}

/// A message Claude wrote for a card. `original` is Claude's text; `edited` is the user's version of it.
struct Draft: Codable, Identifiable, Hashable {
    enum Kind: String, Codable { case opener, reply }

    let id: Int
    var kind: Kind
    var original: String
    var edited: String?
    /// The guardrail checks the text hit, such as `denies_ai`. Nil when not checked.
    var guardrail: [String]? = nil
    /// The app can send it now (ADR 0003): Send. Otherwise the user copies it into the dating app: Copy.
    var sendable = false
    /// Its send time: when autopilot sends it alone, or when it is best sent. Nil from an older server.
    var sendAt: Date?
    /// Why that time, in a few words ("they take their time"); may be empty.
    var timingReason: String?
    /// `pending`, `copied` or `failed` on the card's draft list; also `approved`, `sending`, `sent`, `dismissed`.
    var status = "pending"

    /// What to show and copy: the user's edit when there is one.
    var text: String { edited ?? original }

    /// The server never sends it until the user edits it.
    var deniesAI: Bool { guardrail?.contains("denies_ai") == true }
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
    /// `confidence` as the server words it for the card: Sure, Likely or Guess.
    var confidenceWord: String

    /// What to show and use: the user's correction when there is one.
    var text: String { corrected ?? value }

    /// The kind as a label: `texting_style` reads "Texting style".
    var title: String {
        let words = kind.replacing("_", with: " ")
        return words.prefix(1).uppercased() + words.dropFirst()
    }
}

/// One thing that waits for the user's review: `draft`, `copied_draft`, `failed_send`, `handover` or `paid_item`.
/// The server adds more kinds later.
struct QueueItem: Codable, Identifiable, Hashable {
    var kind: String
    /// A hot lead: the server pushed it at once.
    var hot: Bool
    /// Nil when `kind` is `paid_item`: a profile to swipe on is not a card.
    var cardID: Int?
    var cardName: String
    /// The card summary, for the face, the dating app and opening the card. Nil when `cardID` is.
    var card: Card?
    /// Set when `kind` is `draft`, `copied_draft` or `failed_send`.
    var draft: Draft?
    /// The match's message the item is about: the one a reply answers, or the one that fired a handover.
    var message: QuotedMessage?
    /// Set when `kind` is `handover`: the server's codes for the handover checks `message` hit.
    var triggers: [String]?
    /// Set when `kind` is `handover`: the suggested replies.
    var suggestions: [String]?
    /// Set when `kind` is `paid_item`.
    var paidItem: PaidItem?

    var id: String { "\(kind)-\(draft?.id ?? paidItem?.id ?? cardID ?? 0)" }

    // The key strategy turns `card_id` into `cardId`.
    enum CodingKeys: String, CodingKey {
        case kind, hot, card, draft, message, triggers, suggestions, paidItem
        case cardID = "cardId"
        case cardName
    }
}

/// A message from the match, quoted on a Review item.
struct QuotedMessage: Codable, Hashable {
    var body: String
    var sentAt: Date
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
    /// The swipe candidate the item is for, whose profile Review opens. Nil for a Boost.
    var candidateID: Int?
    /// The candidate's first photo. Nil for a Boost or a profile without photos.
    var photoUrl: URL?
    /// What the item costs, in the dating app's words ("$1.99"). Nil when the app did not report it.
    var cost: String?

    var title: String { "\(item.replacingOccurrences(of: "_", with: " ").capitalized) on \(app.capitalized)" }

    enum CodingKeys: String, CodingKey {
        case id, app, item, name, reason, status, photoUrl, cost
        case candidateID = "candidateId"
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
    /// Nil when the dating app does not say.
    var age: Int? = nil
    var distanceMi: Int? = nil
    /// The Super Like proposed for this profile, while it waits for the user's answer.
    var paidItem: PaidItem? = nil

    /// "Eve, 30", or the name alone when the app gives no age.
    var nameAndAge: String { age.map { "\(name), \($0)" } ?? name }

    /// "5 mi · Tinder". Miles become km where the locale says so.
    var details: String {
        let distance = distanceMi.map {
            Measurement(value: Double($0), unit: UnitLength.miles).formatted(.measurement(width: .abbreviated, usage: .road))
        }
        return [distance, app.capitalized].compactMap(\.self).joined(separator: " · ")
    }
}

/// How the Swipe tab shows swipe candidates (ADR 0004). Raw values match the server's.
enum SwipeLayout: String, Codable, CaseIterable, Identifiable {
    case oneAtATime = "one_at_a_time"
    case list

    var id: Self { self }
    var title: String { self == .list ? "List" : "One at a time" }

    var summary: String {
        switch self {
        case .oneAtATime: "One person per screen with large photos. Pass or Like, then the next."
        case .list: "Everyone in one list with the suggestion picked. Accept them all at once."
        }
    }
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

    static func dollars(_ usd: Double) -> String {
        // en_US: "$30", not "US$30" outside the US. The app is not localized.
        usd.formatted(
            .currency(code: "USD").locale(Locale(identifier: "en_US"))
                .precision(.fractionLength(usd == usd.rounded() ? 0 : 2)))
    }
}

/// One dating app on Connected apps: its connector state and, while `broken`, the alert that stopped it.
struct ConnectedApp: Codable, Identifiable, Equatable {
    let app: String
    let state: ConnectorState
    let alert: ConnectorAlert?

    var id: String { app }
}

/// Raw values match the server's `state`. `copilotOnly` is the user's choice; `noConnector` apps always draft and copy.
enum ConnectorState: String, Codable {
    case connected, broken
    case copilotOnly = "copilot_only"
    case notConnected = "not_connected"
    case noConnector = "no_connector"
}

/// Why a connector stopped. `reason` is `auth failure` (the session ended) or `ban signal`.
struct ConnectorAlert: Codable, Equatable {
    let reason: String
    let createdAt: Date
}

/// One message of the status strip: something that stops autopilot now. The server sends them in the strip's
/// order; the app holds the copy for each `kind`.
struct StatusMessage: Codable, Equatable {
    enum Kind: String, Codable {
        case paused
        case budgetReached = "budget_reached"
        case connectorAlert = "connector_alert"
    }

    let kind: Kind
    /// `paused`: the paused app, nil for all apps. `connectorAlert`: the app whose connector stopped.
    let app: String?
    /// `budgetReached`: when the next month's budget starts.
    let resetsAt: Date?
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

    /// The purge button names who it deletes: "Delete everything about Ada and Bea".
    static func button(names: [String]) -> String {
        // en_US: the app is not localized.
        "Delete everything about \(names.formatted(.list(type: .and).locale(Locale(identifier: "en_US"))))"
    }
}

/// The settings the app reads from `GET /settings`; the server sends more, which the app ignores here.
struct UserSettings: Decodable, Equatable {
    /// Hot-lead and handover pushes name the match. Off: "Someone replied. A draft is ready."
    var pushNamePreviews: Bool
    /// Faces stay blurred until tapped (ADR 0009). See `BlurredFace`.
    var blurPhotos: Bool
    /// The night window: autopilot sends nothing from this hour until the end hour, 0 to 23, in the user's time
    /// zone. A start after the end wraps past midnight.
    var nightWindowStart = 1
    var nightWindowEnd = 7
}

/// One action the app took toward a dating app or the calendar, and what triggered it (`GET /audit-log`).
struct ActivityEntry: Decodable, Identifiable, Equatable {
    var id: Int
    var type: String
    var app: String
    /// Who or what was acted on: `card:7`, `candidate:3`, `bio`, `photo:4`, `account`.
    var target: String
    var trigger: String
    var createdAt: Date
    /// The person the entry is about, as named now. Nil for the user's own things and for a purged person.
    var name: String?

    /// What the app did, in words: "Sent Ada a message".
    var summary: String {
        let who = name ?? "someone"
        switch type {
        case "message": return "Sent \(who) a message"
        case "like": return "Liked \(who)"
        case "pass": return "Passed on \(who)"
        case "super_like": return "Sent \(who) a Super Like"
        case "rose": return "Sent \(who) a Rose"
        case "boost": return "Boosted your profile"
        case "profile_change": return target == "bio" ? "Changed your bio" : "Changed a photo"
        case "calendar_hold":
            // `card:7 hold 2026-12-01T19:00:00+00:00`
            switch target.split(separator: " ").dropFirst().first {
            case "hold": return "Held a time for \(who)"
            case "release": return "Released a time held for \(who)"
            case "confirm": return "Confirmed the date with \(who)"
            default: return "Changed your calendar for \(who)"
            }
        case "purge": return "Deleted someone's data, as they asked"
        default: return type
        }
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
    /// The photo's place on the profile, 1 the lead photo: Claude's ranking or the user's order, whichever came
    /// last. nil until either.
    var rank: Int?
    /// Why Claude ranked the photo where it did. nil until ranked.
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

/// A bio and prompt answers for one dating app: what the user accepted, or a rewrite on offer.
struct Bio: Codable, Equatable {
    var bio = ""
    /// Prompt -> answer, keyed by the prompt's exact text.
    var prompts: [String: String] = [:]
}
