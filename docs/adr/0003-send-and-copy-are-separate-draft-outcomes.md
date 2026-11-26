# Send and Copy are separate draft outcomes

In v1 one "Approve" sent a draft on a card the app could send to, and on any other card only marked it approved, after which no screen showed it again. The user could not tell which had happened and lost the text. Now every draft action is named for its effect: **Send** where the app can send (a failed send stays in view with Retry and Copy), **Copy** where it cannot (no connector, a card not linked to a match, or a broken connector). A copied draft stays on its card and in Review until a newer message from the user appears in the chat or the user clears it, which needs a server rule that clears copied drafts. Copy stays needed after the Hinge connector ships, for Bumble, screenshot-only cards and connector outages.

## Considered options

- Copy, then remove the draft with a toast: simplest, but a forgotten paste loses the text again.
- Keep one Approve button and add a separate "Approved" list: keeps the ambiguity about whether a message went out.
