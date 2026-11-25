# Audit of the redesign mockups

2026-11-25. This reviews the first full set of redesign mockups (Today, Review, Pipeline, Card detail, Swipe, You), drawn after the grill and spec [#44](https://github.com/stratastef/dating-crm/issues/44). It is not a review of the v1 app; that is [ui-audit.md](ui-audit.md).

The review combined three methods: an `impeccable` critique (Nielsen heuristics and design specificity), an `apple-design` review against the HIG (color, Liquid Glass, generative AI, accessibility, layout), and the `frontend-design` checklist of templated defaults. The mockups were static HTML; motion, dark mode and Dynamic Type were not drawn.

## Verdict

The structure is right: the information architecture and states fix the v1 audit's P0 and P1 findings. The look is not yet authored. Every screen is white rounded cards on grey, in iOS default blue, with gray initials for people. Swap the strings and it could be any CRM.

**Heuristic score: 22/36** (Error recovery not scored: no error states were drawn).

| # | Heuristic | Score | Key issue |
| --- | --- | --- | --- |
| 1 | Visibility of system status | 3 | Status strip, badges and the undo toast work. The planned send time is not drawn yet. |
| 2 | Match with the real world | 3 | Mostly plain words. "Handover · personal info asked" is still system language. |
| 3 | User control and freedom | 3 | Undo send, Hold, Clear. |
| 4 | Consistency and standards | 2 | Blue means "needs you", "tap me", "selected tab" and "Send". The AI marker is phrased three different ways. |
| 5 | Error prevention | 3 | The 5-second send window; Like and Pass are buttons, not drags. |
| 6 | Recognition rather than recall | 2 | People are grey initials. Meta strings bury the stage and app. |
| 7 | Flexibility and efficiency | 2 | No row swipe actions or search drawn. |
| 8 | Aesthetic and minimalist design | 2 | Every item has the same weight and the same card. |
| 9 | Error recovery | n/a | Not drawn. |
| 10 | Help and documentation | 2 | The autonomy descriptions and good-date definition only appear on You. |

## Priority issues

1. **P1 One accent color carries four meanings.** System blue marks "needs you", links, the selected tab and the Send button. The grill reserved the accent for "needs you", so it can no longer stand out. HIG, Color: "Avoid using the same color to mean different things." Fix: keep the accent for Waiting for you, hot leads and the review count. Use neutral fills for primary buttons and let the tab bar use its system tint.
2. **P1 People have no faces.** Every row shows a 34 pt grey circle with initials, so the user must read every name in an app about recognizing people. Fix: show the match's first photo at 44 pt or larger wherever a person appears, falling back to initials only when there is no photo.
3. **P1 Templated surface.** Identical white rounded cards for every item, whatever its kind (the frontend-design "SaaS card kit" pattern), plus meta strings joined with middle dots ("Chatting · Tinder · matched 6d ago"). Fix: use plain inset lists for lists. Give each Review item kind its own form, so a draft looks like a message and a handover looks like an alert. Split meta strings into separate lines or an app glyph.
4. **P1 Touch targets.** Review's Dismiss, Edit and Send buttons are about 28 pt tall. Fix: make primary actions full-width 44 pt buttons, and move secondary ones into row swipe actions or a menu.
5. **P2 Too many layers at the bottom of the card.** The tab bar, docked composer and undo toast stack at the bottom of the card, and the status strip joins them on other screens. HIG, Liquid Glass: "Use Liquid Glass effects sparingly", and keep it out of the content layer. Fix: hide the tab bar on the card detail (it is pushed), and show the undo toast in the composer's place rather than above it.
6. **P2 The AI marker is inconsistent.** It reads "AI draft", "Sent by autopilot", or a bare sparkles icon inside a sentence. HIG, Generative AI: "Communicate where your app uses AI." Fix: one component, the sparkles symbol plus a fixed label, with a set list of labels (AI draft, Autopilot, AI suggests).
7. **P2 Flat type scale.** Names at 15 pt medium, lines at 13 pt, captions at 12 pt; only the title is large. Fix: names at body semibold, status lines at subheadline, captions at footnote secondary, plus one larger element per screen (Today's next date, Review's count).
8. **P3 Today's review row looks like a list item.** Fix: give it its own treatment at the top of Today.

## Not drawn yet

Dark mode, the largest text sizes, VoiceOver order, error states, loading and empty states, the planned-send timing (ADR 0008), sign-in and setup.

## Outcome

An `apple-design` review of the refined variant followed. Its findings:

- one attention color only;
- real system glass instead of flat translucency;
- stacked rows at accessibility text sizes;
- spoken labels for the AI marker and planned times.

The owner then compared A2 with three overdrive takes ([a2-and-overdrive.html](mockups/a2-and-overdrive.html)) and chose a combination, A3 ([a3-combined.html](mockups/a3-combined.html)). The decision is recorded in ADR 0009.
