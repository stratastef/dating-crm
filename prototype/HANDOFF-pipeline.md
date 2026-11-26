# Handoff: Pipeline prototype result

> Generated: 2026-11-25
> From: the Pipeline prototype session, for the grill session's `/to-spec` and `/to-tickets`.
> This settles the parked question "Pipeline form".
> Intended path: `/Users/stefan/Downloads/dating-crm/.claude/worktrees/ui-redesign-grill-89b54c/HANDOFF-pipeline.md`. A worktree-isolation hook blocked the prototype session from writing there, so copy this file there.

## Decision

The Pipeline becomes **variant B, Agent status**: it groups cards by who acts next, and the stage is secondary information in each row.

The owner tried three variants on the `iPhone 18 Pro` simulator with the seed data:

- A: collapsible stage sections.
- B: rows grouped by who acts next.
- C: A's stage sections with B's status line in each row.

A and C are rejected.

### Why B

The owner gave these reasons:

- B shows the agent at work. Each row says what autopilot is doing on that chat without opening it.
- B says who acts next. That answers "what do I have to do" faster than stage sections.
- B shows which chats moved off the app, where autopilot cannot see them.

The owner did not say that stage is noise. The stage stays visible, in each row's caption.

## Grouping rules (confirmed by the owner)

The groups appear in this order. Each header shows a count and collapses when tapped. A group with no cards is hidden.

1. **Waiting for you.** It is first, and its header uses the accent color, which is kept for "needs you". It holds every card that is blocked on the user, whatever its stage. A card goes here if any one of these applies, checked in this order (the first match sets the row's reason line):
   1. A handover is pending.
   2. A draft waits in Review.
   3. A copied draft has not been sent yet.
   4. The card is Stalled.
   5. The next action is overdue.
   6. A Dated card has no rating yet.

   A Review item wins over the stage. For example, a Number swapped card with a draft in Review goes here and not to off-app.

   A next action that is due **today** does not move the card here. Today already lists it. It moves once it is overdue. The owner confirmed this rule: "Waiting for you" means the card is blocked on the user, not merely scheduled.
2. **Autopilot is handling.** Matched and Chatting cards that are not in Waiting for you.
3. **You're texting off-app.** Number swapped, Date set, Dated and Seeing them cards that are not in Waiting for you.
4. **Archived.** Collapsed by default.

Inside each group, hot leads come first, then the card with the most recent activity.

## Row content (confirmed by the owner)

- **Avatar**: the match's initial in a circle. A photo replaces it once cards have one.
- **Name**, with a **relative time** on the right ("10m", "2h", "4d"). The time comes from the last message, or the last stage change when there are no messages.
- **Status line**: one line, with a different source for each group:
  - Waiting for you shows the reason only, not the last message (the owner chose this):
    - "Handover · Asked if I'm a bot"
    - "✨ Reply ready in Review"
    - "Copied draft · not sent yet"
    - "Stalled · revive or archive"
    - the overdue next action's text
    - "Rate the date"
  - Autopilot is handling shows the AI marker (the `sparkles` symbol plus the label "Autopilot"), what autopilot is doing, and the chat's topic, for example "✨ Autopilot · sent 4d ago, no reply yet · talking museums". Other forms are "drafting a reply to Lena" and "writing an opener". The owner keeps the topic, which needs a new server field (see below).
  - You're texting off-app shows the next action and its due day ("Confirm the booking · Fri"). Without a next action it shows "Date rated 5/5", or else "No next action".
- **Caption**: the stage and the dating app, for example "Chatting · Tinder". The owner keeps both.
- **Badges**: each badge has an icon and a text label, so it never relies on color alone. The label text uses the primary color for contrast. The badges are:
  - Hot: `flame.fill`, accent icon.
  - Stalled: `pause.circle`, gray icon.
  - Overdue Nd: `exclamationmark.circle`, accent icon.

## API gaps the spec must cover

The prototype worked around these gaps on the client. Each workaround is marked `// prototype:` in the code.

- `GET /cards` has no last message (sender, body, `sent_at`). The prototype made one `GET /cards/{id}/messages` call per card.
- No field gives the chat topic. The prototype used invented topics for Lena and Clara. The owner wants a short topic summary per chat.
- No field says what autopilot is doing on a card: drafting, sent and waiting, or writing an opener. The prototype derived this from who sent the last message.
- No route shows copied drafts on a card (drafts approved on a card the app cannot send to). The prototype hard-coded Maya's draft.
- Hot lead and pending-draft state come from `GET /queue`. The prototype joined them to cards on the client. A field on the card would avoid that.
- The iOS `Card` does not decode `stalled` or `stage_changed_at`, and `Message` does not decode `sent_at`. The shared decoder only parses plain days, so the prototype kept the timestamps as strings.

## Open question for `/to-spec`

What should "Autopilot is handling" show when chat autonomy is Copilot or Off, or when autopilot is paused or at the budget cap? The seed's chat autonomy is Copilot, and the prototype pretended it was Autopilot. The owner was not asked this.

## Prototype

- Branch `prototype/pipeline-board`, in the worktree `/Users/stefan/Downloads/dating-crm/.claude/worktrees/pipeline-prototype-1f08df`. It is not merged, not pushed and has no PR.
- Commit `b47299a`: the three variants behind a Debug-only floating switcher, with the choice kept in `@AppStorage`.
- Commit `6b47ae6`: the owner's grouping rules applied to B.
- Files: `ios/DatingCRM/Screens/BoardView.swift` and `ios/DatingCRM/API/Models.swift`. No server code, database or other screen was changed.
- The variant code is throwaway. Rewrite it properly when the spec is implemented; do not promote it.

## Resolved after the prototype (grill session)

The open question above is settled. "Autopilot is handling" holds only cards autopilot can act on now. Matched and Chatting cards where the match owes a reply and autopilot cannot act go to a new group, **Waiting for them**, with no AI marker. It sits between "Autopilot is handling" and "You're texting off-app". Autopilot cannot act when chat autonomy is Copilot or Off, when autopilot is paused or at the budget cap, or when the app has no working connector. See ADR 0007 and `GLOSSARY.md`.
