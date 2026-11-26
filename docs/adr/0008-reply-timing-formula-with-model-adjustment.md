# Send times come from a formula the draft model may adjust, inside hard bounds

v1 autopilot replied seconds after a match's message synced, which reads like a bot. Each send now gets a send time:

1. A formula sets the default from measurable signals: the match's recent reply gaps, the time since their last message, how engaged their messages are, and the hour of day.
2. The model that writes the draft may move that time within a limited range and gives a one-line reason, because dryness and engagement are hard to measure.
3. The server then clamps the result to hard bounds that no model output can cross:
   - at least 2 minutes if the match is live, otherwise at least 10 minutes;
   - at most 12 hours;
   - never inside the user's night window, 01:00–07:00 by default.

Openers go out at a random time 30 minutes to 6 hours after the match, outside the night window, and never several in the same minute.

The user sees each planned send with its time and reason, and can send it now or hold it. Their own drafts get a suggested send time they can schedule.

## Amended 2026-11-25 (owner's decision)

- A live match at night: when the match wrote in the last 5 minutes, an autopilot reply goes out at the live pace even inside the night window. Otherwise the night window holds. Openers never go out inside it.
- The 12-hour ceiling and the night window: when moving a time past the window's end would put it more than 12 hours out, it goes a few random minutes before the window starts instead, if that is still after the floor; only failing that, to the window's end.
- The same rule is asked again when a planned send goes out, so a night window or time zone changed after planning still holds.

## Considered options

- Instant replies (v1): look automated.
- A fixed random delay: ignores the conversation.
- The model alone: nuanced, but not predictable or testable. The formula keeps a floor of predictability, and the bounds keep the model from sending at 3 a.m. or after a day of silence.
