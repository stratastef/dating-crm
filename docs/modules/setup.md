# Setup

The steps that take a new user from sign-in to a working pipeline on the phone (ADR 0001). The server says which are done in `app/setup.py`; the app runs them in `ios/DatingCRM/Screens/SetupView.swift`.

| Route | Does |
| --- | --- |
| `GET /setup` | `[{"step", "done"}]`: the five steps in order, each done or not. |
| `PATCH /settings {"setup_dismissed": true}` | Hides "Finish setup" on Today. `false` shows it again. |

A step is done once its condition holds, and not before:

| `step` | Done when |
| --- | --- |
| `dating_apps` | A dating app is connected or the user chose copilot-only for it: any app whose state on `GET /connectors` is `connected` or `copilot_only`. Tinder is the only app with a connector, so choosing copilot-only for it counts. A broken connector does not. |
| `calendar` | Google Calendar is connected (`GET /calendar`). |
| `voice` | The voice questionnaire has at least one answer. |
| `preferences` | The user saved preferences once (version 1 or later). |
| `swipe_layout_and_autonomy` | The Swipe layout is chosen and the user set at least one autonomy level. Until then every job runs at its default, which the user never saw. |

Each step reads the route or helper that owns it (`sync.connected_apps`, `calendar.status`, `voice.read_voice`, `current_preferences`, `swipes.read_layout`), so setup and the screen under You never disagree.

**Today's setup summary.** `GET /today` has `setup`: `{"steps_left": n}`, or `null` once the user dismissed it (`users.setup_dismissed`, migration `t70_setup_dismissed`) or no step is left. `setup.summary(user, db)` computes it.

## On the phone

**When setup runs.** Right after a phone number sign-in that created the account (`Session.isNewAccount`, see "Sign-in"), `DatingCRMApp` shows `SetupView` instead of the tabs. Ending setup sets `isNewAccount` back to `false`. After a relaunch it is false, so Today's "Finish setup" is the way back.

**`SetupView(client:finish:)`** loads `client.setup()` and runs the steps not done, in order. Each step is the screen that holds it under You, unchanged: `ConnectedAppsView`, `CalendarView`, `VoiceView`, `PreferencesView`, then one list with `SwipeLayoutSection` and `AutonomySections`. Each screen saves as the user goes (Voice and Preferences also when they disappear), so Next works whether the step was done or skipped. A bar at the bottom says "Step 2 of 5. Skip it if you like: it stays under You." in New York (only "Step 2 of 5" at accessibility sizes) above Next, or Done on the last step. Done stores the autonomy levels as shown, so keeping the defaults counts as choosing them. "Skip setup" in the toolbar ends setup at once. Setup carries `MainTabView`'s root look (`.tint(.primary)`, plain lists, `MotionReducedReader`), since it is shown outside the tabs.

**Finish setup on Today.** Under the review count, a row says "Finish setup" and "3 steps left". It opens `SetupView` full screen on the steps left; Today reloads when it closes. The `xmark` button (44 pt, "Hide Finish setup") calls `client.setSetupDismissed(true)` and shows a toast with Undo.

**Under You.** Every step stays reachable: Connected apps, Calendar, Voice (Profile), Preferences, Swipe layout, and the autonomy levels under Autopilot.

`APIClient`: `setup() -> [SetupStep]` (`step: SetupStep.Step`, `done`), `setSetupDismissed(_:)`; `Today.setup: SetupSummary?` (`stepsLeft`). Tests: `SetupTests`.

**Simulator checks.** Debug builds open setup with `SIMCTL_CHILD_DCRM_SETUP=1`, or on one step with its name (`DCRM_SETUP=swipe_layout_and_autonomy`). Screenshots: `docs/design/screenshots/redesign/t70-{setup,setup-swipe,today-setup}-{light,dark,ax}.png`.

## Limits

- Not tapped on screen: Next, Done, Skip setup, the Finish setup row, the hide button and its Undo. Only the first step, the last step and Today's row were seen, from launch hooks.
- If storing the autonomy levels on Done fails, setup still ends; Today then shows the step as left.
- Large titles truncate at the largest accessibility sizes ("Swipe and a…"), as other pushed screens do.
