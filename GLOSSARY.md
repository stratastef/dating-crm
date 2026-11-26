# Dating CRM

A personal CRM for dating-app matches. It tracks every match as a card and lets an AI draft, send and swipe for the user, at an autonomy level the user sets per job.

## Language

### Matches and the pipeline

**Match**:
A person the user matched with on a dating app.
_Avoid_: Lead, contact

**Card**:
The record of one match on one dating app: its stage, next action, due date and notes.
_Avoid_: Match record, contact, ticket

**Stage**:
Where a card stands: Matched, Chatting, Number swapped, Date set, Dated, Seeing them or Archived.
_Avoid_: Status, column

**Stalled**:
A flag on a card in Chatting, Number swapped or Date set after a set number of days with no message from either side. It is not a stage.
_Avoid_: Dead, cold

**Next action**:
The one thing the user plans to do next on a card, with an optional due date.
_Avoid_: Task, to-do

**Rating**:
The user's 1–5 score and short note on a date, given after it.

**Good date**:
A date the user rates 4 or 5.

### Drafts and sending

**Draft**:
A message the AI wrote for a card, not yet sent.
_Avoid_: Suggestion, reply

**Send**:
The app delivers a draft through the dating app's connector. Only possible on a card linked to a match on an app whose connector works.
_Avoid_: Approve

**Copy**:
The user takes a draft's text to send by hand in the dating app, on a card the app cannot send to.
_Avoid_: Approve

**Copied draft**:
A draft the user copied that does not yet appear in the chat. It stays in view until a newer message from the user appears in the chat or the user clears it.
_Avoid_: Approved draft

**Send time**:
When a draft goes out. For autopilot it is planned from the conversation, or for an opener at a random time 30 minutes to 6 hours after the match; for the user's own drafts it is suggested and can be scheduled.
_Avoid_: Delay, schedule (alone)

**Planned send**:
A draft autopilot will send alone at its send time. The user sees it with its reason and can send it now or hold it, which moves it to Review.
_Avoid_: Queued message

**Scheduled send**:
A draft of the user's that goes out at a send time they chose (Send at), as given, with no five-second Undo. They can cancel it until it goes out, which makes it a pending draft again.
_Avoid_: Planned send (that is autopilot's)

**Live**:
A match who sent a message in the last five minutes.

**Night window**:
The hours in the user's time zone when nothing is sent, 01:00 to 07:00 by default.
_Avoid_: Quiet hours, do not disturb

**Suggested reply**:
A reply the AI offers with a handover, for the user to copy.
_Avoid_: Draft

**Handover**:
Autopilot stopping one chat and passing it to the user because a handover trigger fired. The user then takes over or hands it back.
_Avoid_: Escalation

**Review queue**:
The drafts, handovers and paid items waiting for the user's decision, hot leads first. The rest waits for a batch the user clears a few times a day.
_Avoid_: Inbox, queue (alone)

**Hot lead**:
A card that needs the user live rather than at the next batch: date coordination, a pending handover, or a reply within the last hour.
_Avoid_: Urgent, priority

**Style profile**:
How the user writes, learned from their past chats, their edits to drafts and the voice questionnaire. Every draft is written from it.
_Avoid_: Voice, persona

**Voice questionnaire**:
The setup questions about how the user texts. The style profile needs it before the first draft.

### Autonomy

**Job**:
One kind of work the app can do for the user: chat, optimize profiles, or swipe.
_Avoid_: Feature, module

**Autonomy level**:
How much the app may do alone for one job: Off, Copilot, Autopilot or Full autopilot.
_Avoid_: Mode

**Copilot**:
The autonomy level where the app drafts and suggests and the user sends.

**Autopilot**:
The autonomy level where the app acts alone but hands date logistics and every handover trigger to the user.
_Avoid_: Guardrails

**Full autopilot**:
The autonomy level where the app also coordinates and books dates alone. Handover triggers still apply.
_Avoid_: Full

**Pause**:
Stopping everything the app does alone, for one dating app or for all of them. What the user taps still happens.
_Avoid_: Kill switch

**Guardrail**:
The check on every outgoing draft that holds back a draft that denies being AI, names a protected trait or overpromises.
_Avoid_: Using it for an autonomy level

**AI budget**:
The user's hard monthly cap on AI spend. Autopilot pauses when it is reached.

**Paid item**:
A Super Like, Rose or Boost the app proposes and spends only with the user's approval.

**Activity log**:
The record of every action the app took toward a dating app or the calendar (messages sent, likes, passes, profile changes, calendar holds, paid items, purges) and what triggered each one.
_Avoid_: Audit log, history

### Reading people

**Match read**:
The AI's read of one match: inferences about texting style, interests and values, from their messages and photos.
_Avoid_: Profile, analysis

**Inference**:
One claim in a match read, with its evidence and confidence. The user can correct it.

### Swiping

**Swipe candidate**:
A profile the app found for the user to like or pass, with the AI's suggestion and its reason.
_Avoid_: Profile

**Swipe layout**:
How the Swipe tab shows swipe candidates, as the user chose: one at a time, or a list. One at a time until they choose.
_Avoid_: View mode

### Connecting apps

**Connector**:
The app's link to one dating app through the user's own session. It lets the app sync, send and swipe there; without it the app only drafts for that dating app.
_Avoid_: Integration

**Screenshot import**:
Sharing a dating-app screenshot to the app, which reads it into a card and returns a draft.

### App screens

**Today**:
The first screen: what the user has to do by time, grouped as Overdue, Today and Coming up, with one summary row for the review queue.
_Avoid_: Home, inbox, dashboard, needs you

**Review**:
The screen that shows the review queue.

**Pipeline**:
The screen that shows every card, grouped by who acts next: waiting for you, handled by autopilot, waiting for them, texting off-app, and archived. Each row still shows the card's stage.
_Avoid_: Board

**Waiting for you**:
A card blocked on the user: a pending handover, a draft in Review, a copied draft not yet sent, a failed send, a Stalled card, an overdue next action, a Dated card with no rating, a match's message autopilot is not answering, or a new match autopilot is not writing to. A next action due today does not count until it is overdue. An Archived card waits for the user too while one of these applies.
_Avoid_: Needs you, due

**Handled by autopilot**:
A Matched or Chatting card that autopilot can act on now: chat autonomy is Autopilot or Full autopilot, the app's connector works, the card is linked to its match and has no handover, nothing is paused and the AI budget is not reached.

**Waiting for them**:
A Matched or Chatting card where the match owes a reply and autopilot cannot act on it.

**Off-app**:
A card from Number swapped on, where the user texts the match outside the dating app.

**Dashboard**:
The screen that shows good dates per hour of the user's time over the weeks.

### Accounts

**Waitlist**:
The people who asked for access on the web and wait for an invite code.

**Invite code**:
A one-time code that lets one person create an account.
_Avoid_: Referral code, beta key

**Sign-in code**:
The six-digit code the app texts to the user's phone number to sign them in. Not the same as a dating app's own login code.
_Avoid_: Code (alone), OTP, verification code

**Setup**:
The steps that take a new user from sign-in to a working pipeline: connect dating apps, connect the calendar, answer the voice questionnaire, state preferences, and choose the Swipe layout and autonomy levels.
_Avoid_: Onboarding (for the steps themselves)
