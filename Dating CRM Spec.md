# Dating CRM Spec

Nov 25, 2026 · @Stefan Dj

A near-autonomous CRM for dating profiles. Version 1 is a personal tool running copilot and autopilot on Tinder and Hinge. The public version is a full-autopilot web service: free CRM, paid autopilot.

## Goal and scope

The app optimizes one number: good dates per hour of your time. Proposed definition: a good date is one you rate 4 or 5 out of 5 afterwards.

| Job | What it does | Autonomy options |
| --- | --- | --- |
| Track matches | One card per person: platform, stage, notes, next action, due date | Always on |
| Chat and book dates | Openers, replies, date coordination against your calendar | Copilot, guardrails, full |
| Optimize profiles | Ranks and lightly edits your real photos; rewrites bio and prompts per app | Copilot, guardrails, full |
| Swipe for you | Likes and passes based on your preferences | Off by default; copilot, guardrails, full |

Autonomy is set per job:

- **Copilot:** the app drafts and suggests; you tap to send.
- **Guardrails:** the app acts alone and hands over at the triggers in AI behavior.
- **Full:** the app acts alone up to a booked date; handover triggers still apply.

Out of scope:

- Following a chat off the dating app after numbers are swapped. The CRM keeps notes and reminders; you text.
- AI-generated photos and automatic A/B rotation of photos or bios.
- Any feature that targets a match's insecurities to persuade them.
- Fine-tuning a model in v1. That comes later, once outcome-labeled data exists.

## Architecture

&#91;embedded content: system architecture · iPhone, VPS, outside services\]

Your iPhone talks only to the API. The API and the worker share Postgres as their job queue, and only the worker reaches outside services.

## Connectors

Every app has two paths: a screenshot copilot that always works, and an optional private-API connector that unlocks autopilot. When a connector breaks, that app falls back to copilot.

- **Screenshot copilot:** share a screenshot from the iOS share sheet; the server reads it, updates the match card and returns a draft.
- **Private-API connector:** uses your captured session to read matches and messages, send, like and pass. Each connector declares which of these it supports, so any one can be switched off or left out of a build.

| App | Phase | Session source | Notes |
| --- | --- | --- | --- |
| Tinder | v1, full stack | Web login token, captured from your computer | Most unofficial-API prior art |
| Hinge | v1, built alongside Tinder | Decided by the spike below | Phone-only; certificate pinning likely |
| Bumble | Later | Web login token | Women message first in women–men matches |

Hinge spike, 2–3 days, stop at the first approach that works:

1. The connector runs Hinge's own SMS login; you type the code into the iOS app.
2. A proxy on your iPhone captures the app's session.
3. An Android emulator on the VPS runs the real Hinge app.

If none works, Hinge stays copilot-only.

### Connector tooling

REA (`rea`), a reverse-engineering CLI, covers the analysis side of building each connector. It tells you the API shape; the connector code, cert-pinning bypass and session capture are still yours to build and maintain, and break on each app update. It is a CLI run from the worker or during the spike, not an MCP in the app.

| Target | REA commands | Finds |
| --- | --- | --- |
| Tinder, Bumble (web) | `analyze-web-bundle`, `recover-javascript-sources`, `export-web-scripts` | API endpoints and request signing in the web app JS |
| Any app (traffic) | `inspect-web-network-capture`, `capture-browser-scenario` | The real API calls under your own login |
| Hinge (Android path) | `inspect-android-package`, `decompile`, `inspect-android-method`, `instrument-with-frida`, ADB tools, `capture-adb-screen` | APK internals; Frida is the usual way past certificate pinning, the spike's step-2/3 blocker |
| Hinge (iOS path) | `inspect-macho`, `demangle-swift`, `decode-interface-builder` | Mach-O and compiled UI metadata |

Legal note: REA speeds the reverse-engineering, it does not change its legality. Reverse-engineering these apps breaks their terms; for the public product this is the Match Group exposure already in Risks.

## Match pipeline

Every match is a card that moves through seven stages. Each card carries its stage, next action, due date and notes.

1. **Matched:** new match synced or imported.
2. **Chatting:** the app drafts or sends per the chat autonomy level.
3. **Number swapped:** the app stops chatting; you take over off-app.
4. **Date set:** time and place agreed; the calendar hold becomes an event.
5. **Dated:** the app asks for your 1–5 rating and a short note.
6. **Seeing them:** ongoing; reminders only.
7. **Archived:** unmatched, declined or closed by you.

**Stalled rule:** a card in Chatting, Number swapped or Date set moves to Stalled after a set number of days without a reply. The app then suggests a revive message or archiving. Open question: how many days (proposed: 3).

## AI behavior

A top model (Claude) writes every draft from your style profile, the match read and retrieved examples; v1 trains nothing. Jev runs cheap yes/no checks around it.

### Voice

- Learned from your past chats (via connectors or screenshots), your edits to drafts and a setup questionnaire.
- Each draft gets your style profile, the match read and similar past chats of yours that led to dates.
- Outcome labels (led to a date, its rating) become the dataset for later fine-tuning.

### What you want

Learned from five signals: wishes you state in plain words, a must-have and dealbreaker list, date ratings, your manual swipes and which chats turned into dates.

### Match read

The app reads each match's texting style, interests and values, plus a psych profile from their photos: setting, who is in them, dress and pose. It then sets the reply tone, such as bold, playful or sincere.

- Every inference shows its evidence and a confidence score, and you can correct it.
- People in their photos are context only, never profiled one by one.
- Guesses about protected traits (ethnicity, religion, health, sexuality, politics) are opt-in at signup.
- No targeting of insecurities (out of scope).

### Handover triggers

Autopilot pauses the chat, pings you with suggested replies and offers a take-over button when:

- the match asks whether it is a bot or AI; no suggestion is a flat denial;
- commitments or logistics come up: time, place, exclusivity;
- personal info is swapped: number, socials, address, workplace;
- the topic is sensitive or explicit: sex, health, trauma, politics, hostility.

Where the law requires it, such as the EU, AI involvement is disclosed to matches.

### Jev checks

| Check | Runs on | On a hit |
| --- | --- | --- |
| Draft guardrail | Every outgoing message | Denies being AI, names a protected trait or overpromises → sent to you instead |
| Handover trigger | Every incoming message | Handover as above |
| Hot-lead triage | Every draft | Live push instead of batch queue |
| Swipe pre-filter | Profile bio text | Dealbreaker → pass before any paid photo analysis |

Jev judges one sentence at a time, without the rest of the chat. Messages it checks pass through treg, OpenRouter and Jev's provider.

### Review and spending

- **Review:** hot leads (date coordination, handovers, replies within the last hour) get a live push; the rest waits in a queue you clear 2–3 times a day.
- **Calendar:** every time slot offered to a match gets a tentative hold, released on decline, so two matches never get the same slot.
- **Paid items:** Super Likes, Roses and Boosts only with your approval.
- **AI budget:** hard monthly cap. A cheap model pre-screens swipe profiles; the top model handles chats and deep reads. Autopilot pauses at the cap.

## Data, security and retention

The schema is multi-user from day one, though v1 has one user. Everything is kept, in your setup and in the product.

- **Tenancy:** every row carries a user ID.
- **Session tokens:** encrypted at rest with a per-user key, with the master key kept outside the database. Never logged.
- **Retention:** keep everything, including matches' photos, messages and psych profiles. This makes any breach worse, and it covers people who never signed up.
- **Deletion requests:** a match can ask for their data to be deleted, and privacy law (GDPR in the EU) requires honoring it. The app needs a find-and-purge tool by person.
- **Audit log:** every autopilot action (message, like, pass, profile change, calendar hold) is logged with what triggered it.
- **Kill switch:** one tap pauses all autopilot, globally or per app.
- **Ban detection:** an auth failure or ban signal pauses that app's autopilot and alerts you.
- **Ban consent:** product users explicitly accept the ban risk during onboarding.
- **Backups:** nightly encrypted Postgres backups to object storage.

## Stack and deployment

A SwiftUI app talks to a Python server on your own VPS; one push to main deploys it.

| Layer | Choice | Note |
| --- | --- | --- |
| iOS client | SwiftUI, share extension, push notifications | Your personal build; needs a paid Apple developer account |
| API | Python + FastAPI |  |
| Worker | Python process running connectors and autopilot 24/7 | Jobs queued in Postgres; no extra queue service |
| Database | Postgres | Multi-user schema |
| AI | Claude top model, small model for pre-filters, Jev via treg | Hard monthly cap |
| Calendar | Google Calendar API first | iCloud (CalDAV) and Outlook (Microsoft Graph) later, user's choice |
| Hosting | Your own VPS |  |
| Deploys | Docker Compose, GitHub Actions, Caddy | CI builds images on push to main, SSHes in, runs compose; Caddy serves HTTPS |
| Public client | Web app with Stripe billing | After v1 |

## Milestone plan

The first slice is the full stack on Tinder, with Hinge in a parallel lane. Hinge joins each milestone once its spike succeeds; otherwise it stays copilot-only.

1. **Foundations:** VPS, Docker Compose, GitHub Actions, Caddy, multi-user Postgres schema, token encryption, audit log, kill switch.
   - Exit: a push to main deploys and passes a health check.
2. **Tinder sync and Hinge spike:** Tinder connector reads matches and messages into cards; the Hinge spike runs in parallel.
   - Exit: your Tinder matches show as cards; the Hinge approach is chosen or Hinge is marked copilot-only.
3. **CRM and copilot:** pipeline in the iOS app, screenshot import, voice from past chats and the questionnaire, match read with evidence, date ratings, review queue with push.
   - Exit: you use copilot drafts for every chat for one week.
4. **Chat autopilot:** guardrails and full modes, Jev checks, handover triggers, Google Calendar holds, budget cap, ban detection.
   - Exit: autopilot books a real date with zero guardrail misses in the audit log.
5. **Swipe and profile:** preference list, Jev and cheap-model pre-filters, photo ranking and edits, bio and prompt rewrites, paid-item approvals.
   - Exit: swipe autopilot runs a week within the budget cap.
6. **Learning loop:** your edits, chat outcomes, date ratings and manual swipes feed back into drafts and swipes.
   - Exit: good dates per hour is tracked weekly on a dashboard.

## Public product

The public version is a hosted full-autopilot service, sold as a web app with free CRM and paid autopilot.

- **Distribution:** a web app installed to the home screen, billed through Stripe. TestFlight serves only a small early beta, whose testers then move to the web app. The App Store is out: guideline 5.2.2 requires permission under the dating apps' terms.
- **Pricing:** the CRM and screenshot copilot are free. Subscription tiers unlock autopilot levels and more apps; the AI caps keep each tier profitable.
- **AI disclosure:** location-aware. AI involvement is disclosed where the law requires it. The EU AI Act's transparency rules likely apply from August 2026; confirm with a lawyer before opening each market.
- **Product data:** keep everything, same as your setup, with deletion requests honored.

## Risks and open questions

The largest risk is account bans for breaking the dating apps' terms; it is also the main churn driver for the product.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Account bans for automation | Accounts lost, often permanently; users churn | Ban detection pauses autopilot; per-app kill switch; copilot fallback; explicit user consent |
| Legal action from Match Group (owns Tinder and Hinge) | Public service shut down or sued | Lawyer review before public launch; copilot-only build as fallback |
| Connector breaks after an app update | Autopilot stops for that app | Capability flags; automatic copilot fallback; alerting |
| Hinge access fails | Hinge stays copilot-only | Three-approach spike, 2–3 days |
| Breach of kept data | Matches' messages, photos and profiles and users' tokens exposed | Per-user token encryption; encrypted backups; purge tool |
| Matches feel deceived | Trust breaks at the date | Handover on bot questions; no flat denials; disclosure where required |
| Wrong photo-based inferences | Off-key tone in drafts | Evidence and confidence on every inference; your corrections |
| AI cost overrun | Monthly spend above plan | Hard cap; Jev and cheap-model pre-filters |

Open questions:

- [ ] How many silent days move a card to Stalled? Proposed: 3.
- [ ] Is a good date one rated 4 or 5 out of 5?
- [ ] What do the paid tiers cost?
- [ ] When does Bumble get a connector?
