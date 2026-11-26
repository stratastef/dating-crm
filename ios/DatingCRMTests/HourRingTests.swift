import CoreHaptics
import Testing
@testable import DatingCRM

struct HourRingTests {
    @Test func theHourPatternShipsInTheAppAndLastsUnder600Milliseconds() throws {
        let url = try #require(HourRing.pattern)
        let pattern = try CHHapticPattern(contentsOf: url)

        #expect(pattern.duration < 0.6)
    }
}
