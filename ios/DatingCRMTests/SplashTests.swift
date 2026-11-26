import Testing
@testable import DatingCRM

// The splash hands over to Today once the dot has landed and Today is ready, and never after the animation ends.
struct SplashTests {
    @Test func todayReadyEarlyWaitsOnlyForTheDotToLand() {
        #expect(Splash.wait(ready: true, reduced: false, elapsed: .milliseconds(300)) == .milliseconds(620))
    }

    @Test func todayReadyAfterTheDotLandedCutsAtOnce() {
        #expect(Splash.wait(ready: true, reduced: false, elapsed: .milliseconds(1000)) == .zero)
    }

    @Test func aSlowLoadNeverHoldsTheSplashPastTheAnimation() {
        #expect(Splash.wait(ready: false, reduced: false, elapsed: .zero) == .milliseconds(1200))
        #expect(Splash.wait(ready: false, reduced: false, elapsed: .milliseconds(1100)) == .milliseconds(100))
        #expect(Splash.wait(ready: false, reduced: false, elapsed: .milliseconds(1500)) == .zero)
    }

    @Test func withMotionReducedTheFinishedMarkGoesAsSoonAsTodayIsReady() {
        #expect(Splash.wait(ready: true, reduced: true, elapsed: .zero) == .zero)
        #expect(Splash.wait(ready: false, reduced: true, elapsed: .milliseconds(200)) == .milliseconds(1000))
    }
}
