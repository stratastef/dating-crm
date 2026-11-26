# Visual direction: black and white, one indigo accent, faces in glass

The first redesign mockups were stock iOS: grey grouped lists and system blue for everything. After an audit (`docs/design/redesign-mockup-audit.md`) and three rounds of variants, the owner chose direction A3 (`docs/design/mockups/a3-combined.html`).

- **Color.** The app is black and white, after Hinge's restraint. One indigo accent (`#4F46E5`, `#A5B4FC` in dark mode) marks only what waits on the user: the Waiting for you group, hot leads, overdue times, the review count and Today's counter. Buttons, links and the selected tab never use it. Primary buttons are black capsules (white in dark mode).
- **Surfaces and type.** White plain lists with hairline separators; no grey grouped lists. SF Pro throughout. Apple's New York serif appears only in explanations, empty states and monograms.
- **Faces.** People appear as faces: the lead photo in every row, and full-bleed photos on Review items and the card header ("faces in glass"). A match without a photo gets a monogram on the soft accent. A "Blur photos" setting, off by default, hides faces until tapped.
- **Liquid Glass** is on the functional layer only (tab bar, status strip, toolbar buttons, sticky section headers, sheets, composer, toasts), with one deliberate exception: text plates over photos on Review items and the card header. The owner accepted that departure from the HIG's "no glass in the content layer" for the photo-led look.
- **Motion.**
  - The "living Pipeline": rows spring between groups when their state changes.
  - A planned send drains a ring until its send time.
  - Send shows a five-second undo ring.
  - Today's counter rolls, over a slow color field whose warmth follows the number of waiting items and disappears at zero.
  - Reduce Motion and Low Power Mode replace all of it with plain fades and no field.

## Considered options

- Conversation-first: a time rail and drafts as dashed bubbles.
- Editorial: New York for names, Review one item at a time.
- A2: white surfaces without photo cards.
- Two overdrive takes on their own: the ambient field across all of Today, and faces in glass everywhere.

The owner kept the practical motion and the photo-led Review and card, and dropped the rest.
