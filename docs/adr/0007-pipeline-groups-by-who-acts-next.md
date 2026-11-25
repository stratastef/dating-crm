# The Pipeline groups cards by who acts next, not by stage

A CRM pipeline is normally grouped by stage, and v1 did that. The redesigned Pipeline groups cards by who acts next instead, in this order: Waiting for you, Handled by autopilot, Waiting for them, Texting off-app, and Archived (collapsed). Each row shows its stage and dating app as a caption. The owner compared three SwiftUI variants on the seed data (stage sections, this grouping, and stage sections with a status line). They chose this one because it shows what autopilot is doing on each chat and answers "what do I have to do" faster. The prototype is on branch `prototype/pipeline-board` (`6b47ae6`); it is throwaway code, so do not promote it.

## Consequences

- A card goes to Waiting for you whatever its stage, so a Number swapped card with a draft in Review sits there, not under Texting off-app.
- Handled by autopilot is decided per card (autonomy level, connector, pause, AI budget), so one user can have Tinder chats there and Hinge chats under Waiting for them.
- The API must give each card its last message, what autopilot is doing on it, a short topic of the chat, its copied drafts, and its hot-lead and pending-draft state.
