# Motion and haptics

Notes for the iOS app: the animated splash and a haptics map for the whole app. Nothing here is built yet. The app has no haptics today (no `sensoryFeedback` or feedback generators on the redesign branch), and `ios/DatingCRM/Components/Motion.swift` already reads Reduce Motion.

## Animated splash

The design is the "Animated splash" artboard on the brand canvas.

- **Launch screen.** Keep the generated `UILaunchScreen` blank: plain paper (white, black in dark mode), no logo. iOS can't animate a launch screen. A blank one means nothing jumps when the splash takes over.
- **Splash.** A SwiftUI overlay on the root view, shown on a cold launch only, never when the app resumes.
- **Timing:**
  - 120–640 ms: the ring draws clockwise from just past one o'clock. Use `trim(from:to:)` on the arc, eased in and out.
  - 560–920 ms: the dot lands at one o'clock, scaling to 1.18 and settling at 1. Use a spring with about 0.55 damping.
  - 760–1080 ms: the wordmark rises 8 pt and fades in.
  - About 1.2 s: crossfade to Today.
- **Never longer than the load.** If the session check and Today's data are ready by the time the dot lands (about 0.9 s), cut to Today then. The splash never makes anyone wait.
- **Dark mode:** white ring, `#A5B4FC` dot, on black.
- **Reduce Motion and Low Power Mode:** one 300 ms fade of the finished mark, the same rule as ADR 0009's motion.
- **No haptic on launch.** It would fire on every cold start and mean nothing.

## Haptics

### What to borrow from Duolingo

Duolingo answers every answer at once with the same cue each time: a sound, a color and an animation. It saves a bigger celebration for finishing a lesson. I found no public source on its haptics in particular, so borrow the pattern, not a list of vibrations:

1. **One haptic per meaning.** The same moment always feels the same, so the feel itself carries meaning.
2. **Causal.** A haptic answers something the user just did, or something happening on the screen they are looking at. This follows Apple's guidance on [playing haptics](https://developer.apple.com/design/human-interface-guidelines/playing-haptics). Never for autopilot work in the background.
3. **Always paired with a visible change.** A haptic never stands alone.
4. **Celebrate outcomes, not activity.** The big pattern is kept for a date set and a good date rated. Duolingo's engagement loops stay out: no streaks, no haptic nudges, nothing that pulls the user back (voice rule 5 in [README.md](README.md)).
5. **Quiet by default.** Scrolling, tab switches, navigation and the splash stay silent.

### The vocabulary

Seven system haptics and one custom pattern. Every place in the app uses one of these.

| Name | SwiftUI | Meaning |
| --- | --- | --- |
| tick | `.selection` | Moving through choices: rating steps, autonomy level, picking a time slot |
| tap | `.impact(weight: .light)` | A small act the user can undo: Hold, Copy, Pass, Undo, Hand back |
| press | `.impact(weight: .medium)` | A commit that reaches a match: Send, Send now, Like, Take over |
| thud | `.impact(weight: .heavy)` | A big switch: Pause all, approving a paid item |
| done | `.success` | The thing finished: sign-in code accepted, the last waiting item cleared |
| alert | `.warning` | Needs you now, on the screen you're on: a handover fires in the open chat |
| fail | `.error` | Something failed: send failed, a connector signed out, wrong code, AI budget reached |
| hour | Core Haptics, `HourRing.ahap` | The brand moment: a date set, a good date rated |

**The hour pattern** traces the mark:
- Six light transients over about 360 ms, rising in intensity from 0.3 to 0.6 at sharpness 0.4: the ring drawing.
- One soft, full-intensity transient at about 450 ms, sharpness 0.2: the dot landing.
- Under 600 ms in all. It plays at most a few times a week, which is what keeps it special.

### Where each one goes

| Screen | Moment | Haptic |
| --- | --- | --- |
| Sign in | Code accepted | done |
| Sign in | Wrong or expired code | fail |
| Today | The counter reaches zero because the user cleared the last item | done |
| Review | Send a draft | press |
| Review | Copy a draft | tap |
| Review | Hold or skip | tap |
| Review | Undo inside the five-second ring | tap |
| Card | Send | press |
| Card | Planned send: Send now | press |
| Card | Planned send: Hold | tap |
| Card | Take over a handover | press |
| Card | Hand back | tap |
| Card | A handover fires in the chat that is open | alert |
| Card | A planned send goes out while the user watches | none: the ring empties, and that is enough |
| Pipeline | A row springs into another group | none: background work |
| Swipe | Like | press |
| Swipe | Pass | tap |
| Swipe | Approve a paid item | thud |
| Date rating | Each step | tick |
| Date rating | Submit a 4 or 5 | hour |
| Date rating | Submit a 1, 2 or 3 | tap: no celebration, and no punishment |
| Calendar | A date is set while the app is open (the user confirms, or Full autopilot books it) | hour |
| You | Pause all on | thud |
| You | Pause all off | press |
| You | Change an autonomy level | tick |
| Anywhere | Send failed, connector signed out, AI budget reached | fail |
| Splash | Any | none |

### Building it

- **System haptics:** use SwiftUI's `.sensoryFeedback(_:trigger:)` on the view that changes, triggered by the state the user sees change. Don't wait for the server response. The exceptions are done and fail on sign in, which follow the server's answer.
- **Custom pattern:** the hour pattern is the only one that needs Core Haptics. Use one small helper that loads `HourRing.ahap` into a `CHHapticEngine`, restarts the engine after a reset, and does nothing when `CHHapticEngine.capabilitiesForHardware().supportsHaptics` is false.
- **Settings:** system haptics follow the iPhone's System Haptics switch. Optionally, add a Haptics switch under You, on by default, read by every `sensoryFeedback` through its condition closure. Check on a device whether the custom pattern honors the system switch.
- **Testing:** the Simulator plays no haptics. Check the map on a real iPhone. Each row in the table above is one manual check.
