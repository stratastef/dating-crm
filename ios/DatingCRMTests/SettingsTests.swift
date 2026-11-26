import Foundation
import Testing
@testable import DatingCRM

struct SettingsTests {
    let server = StubServer()

    private func sent() throws -> (method: String?, url: String?, body: NSDictionary?) {
        let request = try #require(server.requests.first)
        let body = try request.httpBody.map { try JSONSerialization.jsonObject(with: $0) as? NSDictionary }
        return (request.httpMethod, request.url?.absoluteString, body ?? nil)
    }

    // Pause.

    @Test func readsWhatIsPaused() async throws {
        server.respond(#"{"all": false, "apps": ["tinder"]}"#)

        let pauses = try await server.client().pauses()

        #expect(pauses == Pauses(all: false, apps: ["tinder"]))
        #expect(try sent().method == "GET")
        #expect(try sent().url == "https://crm.test/autopilot/pause")
    }

    @Test func pausesAllAutopilotWithOneCall() async throws {
        server.respond(#"{"all": true, "apps": []}"#)

        let pauses = try await server.client().setPaused(true)

        #expect(pauses.all)
        #expect(try sent().method == "POST")
        #expect(try sent().url == "https://crm.test/autopilot/pause")
    }

    @Test func pausesAndResumesOneApp() async throws {
        server.respond(#"{"all": false, "apps": ["tinder"]}"#)
        server.respond(#"{"all": false, "apps": []}"#)

        let paused = try await server.client().setPaused(true, app: "tinder")
        let resumed = try await server.client().setPaused(false, app: "tinder")

        #expect(paused.apps == ["tinder"])
        #expect(resumed.apps == [])
        #expect(server.requests.map(\.url?.absoluteString) == [
            "https://crm.test/autopilot/pause?app=tinder", "https://crm.test/autopilot/resume?app=tinder",
        ])
    }

    // Autonomy per job.

    @Test func readsTheAutonomyLevelOfEachJob() async throws {
        server.respond(#"{"chat": "autopilot", "profile": "full_autopilot", "swipe": "off"}"#)

        let levels = try await server.client().autonomy()

        #expect(levels == ["chat": .autopilot, "profile": .fullAutopilot, "swipe": .off])
        #expect(try sent().url == "https://crm.test/autonomy")
    }

    @Test func setsTheAutonomyLevelOfOneJob() async throws {
        server.respond(#"{"chat": "full_autopilot", "profile": "copilot", "swipe": "off"}"#)

        let levels = try await server.client().setAutonomy(job: "chat", level: .fullAutopilot)

        #expect(levels["chat"] == .fullAutopilot)
        #expect(try sent().method == "PUT")
        #expect(try sent().url == "https://crm.test/autonomy/chat")
        #expect(try sent().body == ["level": "full_autopilot"])
    }

    @Test func thePickerNamesTheLevelsAsTheGlossaryDoes() {
        #expect(AutonomyLevel.allCases.map(\.title) == ["Off", "Copilot", "Autopilot", "Full autopilot"])
    }

    @Test func eachLevelHasItsOwnPlainDescription() {
        let summaries = AutonomyLevel.allCases.map(\.summary)
        #expect(Set(summaries).count == AutonomyLevel.allCases.count)
        #expect(summaries.allSatisfy { !$0.isEmpty })
    }

    // Budget and spend.

    @Test func readsTheBudgetAndThisMonthsSpend() async throws {
        server.respond(#"{"spend_usd": 12.5, "cap_usd": 50, "paused": false}"#)

        let budget = try await server.client().budget()

        #expect(budget == Budget(spendUsd: 12.5, capUsd: 50, paused: false))
        #expect(try sent().url == "https://crm.test/budget")
    }

    @Test func setsTheMonthlyCap() async throws {
        server.respond(#"{"spend_usd": 12.5, "cap_usd": 20, "paused": false}"#)

        let budget = try await server.client().setBudgetCap(20)

        #expect(budget.capUsd == 20)
        #expect(try sent().method == "PUT")
        #expect(try sent().url == "https://crm.test/budget")
        #expect(try sent().body == ["cap_usd": 20])
    }

    @Test func showsThisMonthsSpendAgainstTheCap() {
        #expect(Budget(spendUsd: 8.2, capUsd: 30, paused: false).spentOfCap == "$8.20 of $30")
        #expect(Budget(spendUsd: 0, capUsd: 12.5, paused: false).spentOfCap == "$0 of $12.50")
    }

    // Swipe limits.

    @Test func readsTheSwipeLimits() async throws {
        server.respond(#"{"swipes_per_run": 5, "swipes_per_day": 20}"#)

        let limits = try await server.client().swipeLimits()

        #expect(limits == SwipeLimits(swipesPerRun: 5, swipesPerDay: 20))
        #expect(try sent().method == "GET")
        #expect(try sent().url == "https://crm.test/swipes/limits")
    }

    @Test func setsTheSwipeLimits() async throws {
        server.respond(#"{"swipes_per_run": 3, "swipes_per_day": 40}"#)

        let limits = try await server.client().setSwipeLimits(SwipeLimits(swipesPerRun: 3, swipesPerDay: 40))

        #expect(limits == SwipeLimits(swipesPerRun: 3, swipesPerDay: 40))
        #expect(try sent().method == "PUT")
        #expect(try sent().url == "https://crm.test/swipes/limits")
        #expect(try sent().body == ["swipes_per_run": 3, "swipes_per_day": 40])
    }

    // Protected-trait opt-in and AI disclosure.

    @Test func readsAndSetsTheProtectedTraitOptIn() async throws {
        server.respond(#"{"enabled": false}"#)
        server.respond(#"{"enabled": true}"#)

        #expect(try await server.client().protectedTraitGuesses() == false)
        try await server.client().setProtectedTraitGuesses(true)

        #expect(server.requests.map(\.httpMethod) == ["GET", "PUT"])
        #expect(server.requests.map(\.url?.absoluteString) == Array(repeating: "https://crm.test/settings/protected-trait-guesses", count: 2))
        #expect(String(data: try #require(server.requests[1].httpBody), encoding: .utf8) == #"{"enabled":true}"#)
    }

    @Test func readsAndSetsTheAIDisclosure() async throws {
        server.respond(#"{"enabled": true}"#)
        server.respond(#"{"enabled": false}"#)

        #expect(try await server.client().aiDisclosure() == true)
        try await server.client().setAIDisclosure(false)

        #expect(server.requests.map(\.httpMethod) == ["GET", "PUT"])
        #expect(server.requests.map(\.url?.absoluteString) == Array(repeating: "https://crm.test/settings/ai-disclosure", count: 2))
        #expect(String(data: try #require(server.requests[1].httpBody), encoding: .utf8) == #"{"enabled":false}"#)
    }

    // Find and purge.

    @Test func findsAPersonsCardsAndSwipeCandidatesByName() async throws {
        server.respond(#"[{"id": 3, "app": "tinder", "name": "Zelda Fitz", "stage": "chatting", "notes": "", "stalled": false, "hot": false}]"#)
        server.respond("[\(SwipeTests.eve)]")

        let cards = try await server.client().findPeople("zelda fitz")
        let candidates = try await server.client().findCandidates("eve")

        #expect(cards.map(\.name) == ["Zelda Fitz"])
        #expect(candidates.map(\.name) == ["Eve"])
        #expect(server.requests.map(\.url?.absoluteString) == [
            "https://crm.test/people?q=zelda%20fitz", "https://crm.test/people/candidates?q=eve",
        ])
    }

    @Test func purgeSendsTheChosenPeopleWithTheConfirmationAndReturnsHowManyWent() async throws {
        server.respond(#"{"purged": 2}"#)

        let purged = try await server.client().purge(cardIDs: [3], candidateIDs: [7])

        #expect(purged == 2)
        #expect(try sent().method == "POST")
        #expect(try sent().url == "https://crm.test/people/purge")
        #expect(try sent().body == ["card_ids": [3], "candidate_ids": [7], "confirm": "purge"])
    }

    @Test func purgeIsOfferedOnlyOnceTheWordIsTypedAndSomeoneIsChosen() {
        #expect(PurgeConfirmation.allows(typed: "purge", chosen: 1))
        #expect(PurgeConfirmation.allows(typed: " Purge ", chosen: 2))
        #expect(!PurgeConfirmation.allows(typed: "purge", chosen: 0))
        #expect(!PurgeConfirmation.allows(typed: "", chosen: 1))
        #expect(!PurgeConfirmation.allows(typed: "yes", chosen: 1))
    }

    @Test func thePurgeButtonNamesThePeopleItDeletes() {
        #expect(PurgeConfirmation.button(names: ["Ada"]) == "Delete everything about Ada")
        #expect(PurgeConfirmation.button(names: ["Ada", "Bea"]) == "Delete everything about Ada and Bea")
        #expect(PurgeConfirmation.button(names: ["Ada", "Bea", "Cleo"]) == "Delete everything about Ada, Bea, and Cleo")
    }
}
