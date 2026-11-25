# iOS UI audit

2026-11-25, `main` at `38289e1`. Input for the UI redesign: `/grill-with-docs`, then `/prototype`, `/to-spec`, `/to-tickets`, `/implement-spec`.

## How this was done

- **Build:** Debug build of the `DatingCRM` scheme on the `iPhone 18 Pro` simulator, signed in as `dev@example.com` against the local Compose stack.
- **Data:** 13 invented cards across all seven stages and three apps (Tinder, Hinge, Bumble), messages on five cards, three pending drafts (one hot lead), a pending handover, a Stalled card, an overdue due date, a match read with four inferences, three swipe candidates with placeholder photos, a pending Super Like, preferences, a $30 budget cap, three ranked photos (one with an edit on offer), and seven weeks of app time and ratings. Cards and messages went through the API; rows that need Claude or Jev (drafts, inferences, handover, swipe candidates, paid items, photo ranks) were written straight to Postgres, because both services are stubbed. A card called "Sample match" was already there.
- **Review:** every screen opened and used by hand, then reviewed against the `apple-design` guidelines (accessibility, color, layout, typography, feedback, modality, settings, charting, generative AI) and with an `impeccable` critique (Nielsen heuristics, design specificity, personas). The critique ran as a design review only: its detector reads web markup and does not apply to SwiftUI.
- **Contrast** was measured from the screenshots' pixels (WCAG ratio, darkest text pixel against its background).
- **Severity:** P0 blocks a task, P1 causes real difficulty, P2 is an annoyance with a workaround, P3 is polish.
- **Side effect on the dev data:** the Review queue test approved Maya Lindqvist's draft (draft 1). Nothing else was saved.

Screenshots are in [`screenshots/`](screenshots/), numbered in the order taken.

## Summary

The app works as a set of plain SwiftUI forms and lists: every screen loads, nothing crashed, dark mode and Dynamic Type come for free from system components. But it reads like a settings app for a database, not a tool for a person juggling a dozen conversations. The board hides everything that needs attention, the card detail does not show data the server already has, and two core flows dead-end.

**Heuristic score: 14/40 (Poor).** Detail in [Heuristics](#heuristics).

The ten findings that matter most, across screens:

| # | Sev | Finding | Screen |
| --- | --- | --- | --- |
| 1 | P0 | "Write draft" fails with "Answer the voice questionnaire first", but the app has no questionnaire screen. Copilot drafts cannot start from the phone. | Card detail |
| 2 | P0 | Approving a draft whose app cannot send (copilot-only, or no `external_id`) removes it from the queue, and the app shows approved drafts nowhere. The text the user approved is lost to them; they will think it was sent. | Review queue |
| 3 | P1 | The board shows none of the states that need action: hot lead, handover pending, Stalled, overdue due date, unrated date. `Card` in `Models.swift` does not even decode `stalled`. | Board |
| 4 | P1 | A pending draft on a card is invisible on that card. `DraftSection` shows only a draft written in this session. | Card detail |
| 5 | P1 | A saved date rating and note are never shown, and cannot be changed. | Card detail |
| 6 | P1 | The rating sheet only appears when the stage is changed to Dated in this session. A card already in Dated (synced, or "Not now") never asks again. | Card detail |
| 7 | P1 | Match read text renders in button blue at 1.88:1 contrast (evidence and confidence lines), far below 4.5:1. | Card detail |
| 8 | P1 | No screen to connect a dating app (`PUT /connectors/{app}/token`), Google Calendar, voice questionnaire, bios, swipe limits, connector alerts or the audit log. A new user cannot get from install to a working pipeline on the phone. | Missing |
| 9 | P1 | Navigation is seven toolbar items crammed into one glass capsule; Preferences, Photos, Settings and Sign out hide behind "•••". The capsule floats over list content while scrolling and covers section headers. | Board |
| 10 | P1 | No feedback after Copy, Approve, Dismiss, Like, Pass or Save, and no undo. Errors surface as "The server answered with status N." at the top of a long form, often off screen. | All |

## Board (Pipeline)

Screenshots: [`01-board.png`](screenshots/01-board.png), [`02-board-scrolled.png`](screenshots/02-board-scrolled.png), [`03-board-overflow-menu.png`](screenshots/03-board-overflow-menu.png), [`16-board-dark.png`](screenshots/16-board-dark.png), [`17-board-largest-text.png`](screenshots/17-board-largest-text.png).

**Works**
- All seven stages in order with counts; every card opens; pull to refresh.
- Next action is the second line of each row, which is the right thing to lead with.
- Dark mode and the largest accessibility text size both render without clipping.

**Broken**
- Clara Novak is Stalled (server `stalled: true`, suggested actions revive/archive) and shows nothing. `Card` has no `stalled` or `suggestedActions` field, so the app cannot show the flag or the revive/archive offer. (Known v1 gap.)
- Lena Okafor replied ten minutes ago (a hot lead per `is_hot_lead`), Sofia Marchetti waits for a handover, Zoe Tanaka needs a rating: all three look like any other row.
- Clara's due date (Nov 23) is past and looks the same as a future one.
- The overflow menu did not close on a tap outside it or a scroll; only choosing an item closed it.

**Design problems, by severity**
1. **P1 Nothing is prioritized.** The board is a flat list of 7 sections ordered by stage, so the person who needs an answer now can be the 11th row. The spec's goal is good dates per hour of the user's time; the first screen should answer "who needs me now". Design Guideline — Feedback: "Consider integrating status feedback into your interface."
2. **P1 Navigation overload.** Review, Swipe, Dashboard, Preferences, Photos, Settings and Sign out all live in the top toolbar. The pipeline has lost its title once scrolled, and the capsule overlaps the "Date set" header ([`02`](screenshots/02-board-scrolled.png)). Review, the most time-sensitive destination, carries no count. Design Guideline — Layout: "Differentiate controls from content." A tab bar (Pipeline, Review, Swipe, You) fits iOS conventions.
3. **P1 Sign out sits next to Settings** with no confirmation and no destructive styling. Signing back in needs the server URL and API token pasted again.
4. **P2 "Board" is a vertical list.** Seven stages stacked vertically means scrolling past Archived and Seeing them to compare stages. Archived (closed matches) gets the same weight as Chatting.
5. **P2 Row metadata is low-value.** Lowercase app names ("tinder"), full dates with the year ("Due Nov 25, 2026") instead of "Today", "Tomorrow", "2 days late". No photo or initial to recognize a person; no last-message preview or time since last reply.
6. **P2 No row actions.** No swipe actions (archive, move stage), no search or filter by app.
7. **P3 Section headers** are `secondaryLabel` on grouped background at 3.29:1. System default, but the stage name is the board's main structure.
8. **P3 At the largest text sizes** the app name and due date stay side by side and wrap into a ragged block ([`17`](screenshots/17-board-largest-text.png)); stack them vertically at accessibility sizes.

## Card detail

Screenshots: [`04-card-maya.png`](screenshots/04-card-maya.png), [`05-card-maya-read.png`](screenshots/05-card-maya-read.png), [`06-card-write-draft-error.png`](screenshots/06-card-write-draft-error.png), [`07-card-correct-inference.png`](screenshots/07-card-correct-inference.png), [`08-card-handover-sofia.png`](screenshots/08-card-handover-sofia.png), [`09-card-dated-hannah.png`](screenshots/09-card-dated-hannah.png), [`10-rating-sheet.png`](screenshots/10-rating-sheet.png).

**Works**
- Stage picker, next action, due date and notes edit and save; Save is disabled until something changed.
- Handover section on top of a paused card, with suggested replies to copy and Take over.
- Match read shows each inference with evidence and confidence, and tapping one opens a correction alert that saves.
- The rating sheet appears when the stage is changed to Dated.

**Broken**
- **P0 Write draft dead-ends.** It returns "Your style profile is not written yet. Answer the voice questionnaire first." ([`06`](screenshots/06-card-write-draft-error.png)). There is no questionnaire anywhere in the app (`PUT /voice/questionnaire` has no client method).
- **P1 Existing drafts are hidden.** Maya has a pending draft in the Review queue; her card shows only "Write draft" ([`05`](screenshots/05-card-maya-read.png)). Same for approved and failed drafts.
- **P1 Saved rating is invisible.** Hannah Brooks is rated 4 with a note; her card shows neither ([`09`](screenshots/09-card-dated-hannah.png)). There is no way to change a rating.
- **P1 Rating prompt only fires on a stage change.** Zoe Tanaka is in Dated without a rating; opening her card asks nothing. The sheet appeared only after moving her to Date set and back.
- **P1 Match read contrast.** Each inference is a `Button`, so the whole row takes the tint: value in blue, evidence and "82% sure" in light blue `#7FC3FF` on white, 1.88:1 ([`05`](screenshots/05-card-maya-read.png)). Design Guideline — Accessibility: "Strive to meet color contrast minimum standards." It also reads as a list of links.
- **P2 Leaving with unsaved edits discards them silently**, including a stage change made from the rating sheet's "Not now".
- **P2 The draft error** is systemRed `#FF383C` on white at 3.57:1, below 4.5:1 for body text.
- **P3 The card does not refresh after a send.** (Known v1 gap.)

**Design problems, by severity**
1. **P1 Wrong order for the job.** The screen is a settings form: stage and due date first, then notes, a plain message list, the match read, and the draft last. The task on this screen is "reply to this person", so the conversation and the draft belong together and first; pipeline fields are secondary.
2. **P1 Conversation is not a conversation.** Messages are form rows with a "You"/full-name caption, no bubbles, no timestamps, no indication of who wrote last or how long ago. Hard to judge whether a reply is due.
3. **P1 No AI transparency at the point of use.** Drafts, inferences and handover suggestions look like user content. Design Guideline — Generative AI: "Communicate where your app uses AI." and "Raise awareness about and minimize the chance of hallucinations." Confidence exists for inferences but not for drafts.
4. **P2 Handover lacks the why.** "Autopilot paused this chat" does not say which trigger fired (bot question, logistics, personal info, sensitive topic) or quote the message. Suggested replies are centered multi-line button labels ([`08`](screenshots/08-card-handover-sofia.png)); Copy gives no confirmation.
5. **P2 Unlabeled field.** "Next action" is a placeholder-only text field; once filled ("Answer her question about the weekend") nothing says what it is.
6. **P2 Header carries no identity.** Only the name in the inline title: no photo, app, stage or how long since the match.
7. **P2 Rating sheet biases the answer.** It preselects 3, so "Save" records a neutral rating without a choice; 1–5 has no anchors although only 4–5 counts as a good date. Half the sheet is empty ([`10`](screenshots/10-rating-sheet.png)).
8. **P3 Write draft and Read match are offered on every stage**, including Dated, Seeing them and Archived, where the spec says the app stops chatting.

## Review queue

Screenshots: [`11-review-queue.png`](screenshots/11-review-queue.png), [`12-review-queue-scrolled.png`](screenshots/12-review-queue-scrolled.png), [`13-review-after-approve.png`](screenshots/13-review-after-approve.png).

**Works**
- Handovers, hot leads, the paid item and drafts in one list, hot leads first, as the spec asks.
- Drafts edit in place; Approve saves the edit first. The paid item shows its reason and needs an explicit Approve.

**Broken**
- **P0 Approved drafts vanish.** Approving Maya's draft removed it from the list ([`13`](screenshots/13-review-after-approve.png)). Her card has no `external_id`, so `send_approved` queued no send and the draft stays `approved`, which per `app/send.py` means "the user copies it". No screen shows approved drafts, so the user can neither copy nor see it. The UI also never says whether an approve sent the message or not.
- **P1 Sofia's handover is a hot lead** (`is_hot_lead` is true for a pending handover) but its header has no "Hot lead" label, unlike Nora's draft.
- **P1 "Hot lead" label** is orange `#FF8D28` on `#F2F2F7`, 2.07:1. Design Guideline — Color: "Avoid relying solely on color to differentiate between objects, indicate interactivity, or communicate essential information."
- **P2 Mismatched tints:** the Dismiss and Decline icons are blue while their labels are red.

**Design problems, by severity**
1. **P1 No context to decide.** A draft shows only its text and the match's name: not the message it answers, not whether it is an opener or a reply, not the app, not when the match wrote. The user must remember each chat. Tapping the name does not open the card.
2. **P1 No feedback and no undo.** Approve and Dismiss remove the row instantly with no confirmation, toast or undo. Design Guideline — Feedback: "When it makes sense, confirm that a significant action or task has completed." Design Guideline — Undo: "Show the results of an undo or redo."
3. **P2 The paid item lacks what is being bought:** no photo or bio of Amara Diallo, no cost or remaining balance, no link to her swipe profile.
4. **P2 Four item types share one look.** A handover, a hot draft, a paid item and a normal draft differ only in header text. The spec batches the queue to "2–3 times a day", so it should be fast to triage: swipe to approve or dismiss, a count on the board.
5. **P3 The title** collapses from large "Review" to inline on scroll while the board uses the same pattern with a toolbar capsule instead: inconsistent chrome between top-level screens.

## Swipe

Screenshot: [`14-swipe.png`](screenshots/14-swipe.png).

**Works**
- Each profile shows photos, bio, the suggestion and its reason, with Pass and Like. "Find profiles" is in the toolbar; there is an empty state.

**Broken**
- Nothing broke with seeded data. "Find profiles" calls Tinder, which is stubbed, so it was not tried.

**Design problems, by severity**
1. **P1 Suggestion conveyed by font weight only.** The suggested button is bold; Pass and Like are both blue. The user is asked to confirm or override the AI's call, so the call must be unmistakable (label, color and position).
2. **P2 A pending Super Like on Amara is not shown here**, although the paid item names her profile. The two decisions about one person live on two screens.
3. **P2 Missing basics:** no age, distance, app, or which pre-filter decided (`source` is `jev` or `model`). The reason text ("Shares your love of hiking and lives 3 km away") is the only signal.
4. **P2 A scrolling list of profiles** invites skimming many at once; there is no count, no progress and no keyboard-free gesture.
5. **P3 Photos are fixed 150×200 thumbnails** in a horizontal scroll, with no way to view one large.

## Dashboard

Screenshot: [`15-dashboard.png`](screenshots/15-dashboard.png).

**Works**
- Line chart of good dates per hour by week, plus a week list with good dates, hours and rate. Weeks without time leave a gap as intended.

**Broken**
- **P3 "1 good dates"**: no plural handling.

**Design problems, by severity**
1. **P1 No headline.** The app's single success metric has no big number (this week, versus the 4-week average). The chart's y axis runs 0–0.6 per hour; small counts over few hours make a sawtooth that is hard to read. Design Guideline — Charting: "Aid comprehension by adding descriptive text to the chart."
2. **P2 Nothing actionable.** No funnel (matched, chatting, date set, dated), no AI spend versus dates, no hint of what to change.
3. **P2 "Good" is undefined on screen.** Nothing says a good date is a rating of 4 or 5.
4. **P3 Week rows repeat the year** ("Week of Nov 23, 2026").

## Preferences

Screenshot: [`20-preferences.png`](screenshots/20-preferences.png).

**Works**
- Wishes, must-haves and dealbreakers load and edit; blank rows are dropped on save; Save is disabled until something changed.

**Broken**
- Nothing broke.

**Design problems, by severity**
1. **P2 Delete is hidden** behind swipe-to-delete with no Edit button.
2. **P2 No explanation of use.** Nothing says these steer the swipe pre-filter and drafts, or that dealbreakers cause automatic passes.
3. **P2 Versions are invisible.** The server keeps every saved version (`GET /preferences/versions`); the app shows none and gives no confirmation after Save.
4. **P3 Leaving with unsaved edits discards them silently.**

## Photos

Screenshot: [`21-photos.png`](screenshots/21-photos.png).

**Works**
- Photos load from the server in rank order with rank and reason; the suggested edit shows a preview with Accept and Reject; Add and Rank are in the toolbar.

**Broken**
- Nothing broke with seeded data. "Rank" calls Claude, which is stubbed, so it was not tried.

**Design problems, by severity**
1. **P2 Before and after are stacked**, the preview under the original at a different width, so the edit is hard to judge. Side by side or a hold-to-compare would do it.
2. **P2 Accept and Reject are bare text buttons** side by side with no padding, well under the 44 pt touch target.
3. **P2 No delete and no manual reorder.** A photo can only be added.
4. **P2 Half the "Optimize profiles" job is missing:** bio and prompt rewrites (`/bios`) have no screen.
5. **P3 "#1"** as a rank label carries no meaning ("Lead photo" would).

## Settings

Screenshots: [`22-settings.png`](screenshots/22-settings.png), [`23-settings-scrolled.png`](screenshots/23-settings-scrolled.png), [`24-settings-purge-search.png`](screenshots/24-settings-purge-search.png).

**Works**
- Kill switch per app and overall, autonomy per job, budget with spend, privacy switches with a clear footer, and find-and-purge with a typed confirmation word. Each switch calls the server immediately.

**Broken**
- **P2 The purge button reads "Delete 0 and all their data"** before anyone is ticked, and "Delete 1 and all their data" after; it does not name the person.
- **P2 Find results land under the keyboard**; the keyboard does not dismiss on scroll or Return.
- **P3 Spend shows "US$0.00"** next to a bare "30": the cap field has no label or currency once filled.

**Design problems, by severity**
1. **P1 The kill switch is buried.** "Pause all autopilot" is the most important safety control and sits behind two taps (••• › Settings). It belongs on the main screen, with its state visible when autopilot is paused.
2. **P1 Autonomy levels are jargon.** "Copilot", "Guardrails", "Full" with one footer line; the user cannot tell what each level will do for chat versus swipe without the spec. Design Guideline — Generative AI: "Set clear expectations about what your AI-powered feature can and can't do."
3. **P2 Mixed concerns.** Day-to-day controls (pause, autonomy, budget) share a screen with a GDPR deletion tool. Purge should be its own screen.
4. **P2 Budget lacks context:** spend is not shown against the cap ("$0 of $30"), no projection, no history.
5. **P2 Apps without a connector** (Bumble) get a pause switch that does nothing, since the app never acts alone there.

## Missing screens

Server features with no screen in the app. The redesign needs to decide which belong on the phone.

| Feature | Route | Effect of the gap |
| --- | --- | --- |
| Voice questionnaire | `PUT /voice/questionnaire`, `GET /voice` | P0: drafts cannot be written until it is answered. |
| Connect a dating app | `PUT /connectors/{app}/token` | P1: sync cannot start from the phone. |
| Google Calendar | `/calendar/connect` | P1: calendar holds cannot be set up from the phone. |
| Add a card by hand | `POST /cards` | P2: Hinge (copilot-only) cards come only from shared screenshots. |
| Bios and prompts | `/bios/{app}` | P2: half of "Optimize profiles". |
| Swipe limits | `/swipes/limits` | P2 |
| Connector alerts | `GET /connectors/alerts` | P2: the user is not told when Tinder stops working. |
| Audit log | `GET /audit-log` | P2: no record of what autopilot did alone. |
| Preference versions | `GET /preferences/versions` | P3 |

Not audited: Sign-in (needs the API token typed into the simulator), the share extension and push (both need a signed build on a device, see `ios/README.md`).

## Heuristics

From the `impeccable` critique, scored 0–4 across the whole app.

| # | Heuristic | Score | Key issue |
| --- | --- | --- | --- |
| 1 | Visibility of system status | 1 | Hot lead, handover, Stalled, overdue and unrated states are invisible on the board; no feedback after actions. |
| 2 | Match between system and real world | 2 | Stage names fit; "Kill switch", "Guardrails", "Match read", "Rank" are internal terms. |
| 3 | User control and freedom | 1 | No undo on approve or dismiss; unsaved edits dropped silently; ratings cannot be changed; sign out without confirmation. |
| 4 | Consistency and standards | 2 | Save-button screens next to save-on-toggle screens; icon and label tints differ; top-level screens use three different chrome patterns. |
| 5 | Error prevention | 2 | Purge has a typed confirmation; the rating sheet preselects 3; approve gives no warning that it will not send. |
| 6 | Recognition rather than recall | 1 | Review items without the message they answer; unlabeled next action; destinations hidden in "•••"; delete hidden behind a swipe. |
| 7 | Flexibility and efficiency | 1 | No row swipe actions, search, filters or batch triage. |
| 8 | Aesthetic and minimalist design | 2 | Clean system styling, but every element has the same weight and the card detail is one long form. |
| 9 | Error recovery | 1 | The draft error points to a screen that does not exist; other errors are "The server answered with status N." at the top of the form. |
| 10 | Help and documentation | 1 | Settings footers only; nothing explains autonomy, the match read or what a good date is. |
| | **Total** | **14/40** | **Poor:** major UX overhaul needed. |

**Design specificity.** Category-interchangeable. Every screen is a stock grouped `List` or `Form` with default tint and type; swap the strings and it is a CRM for plumbers. Nothing reflects that this is about people and conversations: no faces, no chat, no sense of momentum or urgency, no warmth. The product's one number (good dates per hour) appears only on the third toolbar item.

## Personas

- **Owner on the go (distracted mobile user):** opens the app between meetings to see who needs a reply. The board gives no answer; Review has no count; a hot lead looks like any row. Approving a draft gives no sign whether it went out.
- **First-time user:** after sign-in, an empty board with no way to connect Tinder, set up the voice questionnaire or calendar. "Write draft" fails with an instruction they cannot follow.
- **VoiceOver / large-text user:** match read and hot-lead text fall below 2:1 contrast; suggestion on Swipe is conveyed by font weight only; Accept and Reject on Photos are under 44 pt.

## Questions for the grill

- What is the first screen for: the pipeline by stage, or a "needs you now" inbox that merges hot leads, handovers, Stalled cards, due next actions and unrated dates?
- Should Review stay a separate destination, or become the top of the board?
- Is the card detail a chat screen with CRM fields attached, or a CRM record with the chat attached?
- Which of the missing screens belong on the phone (voice questionnaire, connecting apps, calendar, bios), and which stay web or CLI?
- Where does the kill switch live, and how does the app show that autopilot is paused or at the budget cap?
- How should AI content be marked everywhere (drafts, inferences, suggestions), and how much confidence should be shown?
- Does Swipe stay a list, or become one profile at a time?
- What should "approved but not sent" look like, and where do approved drafts live until copied?
- What personality should the app have: a calm tool, or something warmer that fits dating?
