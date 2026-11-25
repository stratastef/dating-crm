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

## Considered options

- Instant replies (v1): look automated.
- A fixed random delay: ignores the conversation.
- The model alone: nuanced, but not predictable or testable. The formula keeps a floor of predictability, and the bounds keep the model from sending at 3 a.m. or after a day of silence.
