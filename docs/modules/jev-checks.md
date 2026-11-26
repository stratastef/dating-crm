# Jev checks

Jev is a cheap yes/no classifier reached through treg. It judges one sentence at a time and never sees the rest of the chat. All of it is in `app/jev.py`; `ask()` is the one function that calls Jev.

| Function | Use it for | Returns |
| --- | --- | --- |
| `jev.ask(sentence, check)` | One yes/no check on one sentence. `check` is a key of `jev.CHECKS`; add a key to add a check, for example a bio dealbreaker. | `bool`. Raises `JevUnavailable` when Jev is not configured or the call fails. |
| `jev.guardrail_hits(db, user_id, text)` | Draft guardrail on an outgoing message. | The checks hit, from `denies_ai`, `protected_trait`, `overpromise`, `plays_on_insecurity`. Empty means safe to send. |
| `jev.read_hits(db, user_id, text)` | Limits of the match read, on one inference's value and evidence. | The checks hit, from `about_other_person`, `guesses_protected_trait`, `targets_insecurity`. |
| `jev.handover_hits(db, user_id, text)` | Handover trigger on an incoming message. | The checks hit, from `asks_if_ai`, `logistics`, `place_or_exclusivity`, `personal_info`, `sensitive`. Empty means no handover. |
| `jev.is_hot_lead(db, user_id, text)` | Hot-lead triage on a draft. | `bool`: the draft deserves a live push. |
| `jev.dealbreaker_hit(db, user_id, bio, dealbreakers)` | Swipe pre-filter on a candidate's bio. | The first dealbreaker the bio shows, else `None`. `None` too when Jev could not be asked: the cheap model then screens the profile. With `strict=True` it raises `JevUnavailable` instead; swipe autopilot uses that. |

- The three functions split the text into sentences and ask about each. A check is hit if any sentence hits it.
- Results are stored with the row. `messages.handover` is set for a new message from `them`, by `POST /cards/{id}/messages` and by `upsert_message`, if the user has not answered it yet and it is at most a day old. It is `null` (not checked) for an older or answered message and for the user's own messages. `drafts.guardrail` and `drafts.hot_lead` are set when a draft is written, and `PATCH /drafts/{id}` runs the guardrail again on the edit. The routes return these fields.
- Never send a draft unattended whose `guardrail` is not an empty list: `queue_send(..., unattended=True)` enforces it. Code that sends any other text must call `jev.guardrail_hits()` on it first.
- Fail closed: when Jev is not configured or a call fails, `guardrail_hits` and `handover_hits` return `["unavailable"]`, which counts as a hit, and `is_hot_lead` returns `False`. Nothing is sent unattended without Jev.
- The owner must set three variables for the API and the worker; Compose passes them through from your shell or `.env`. Until all three are set, every check fails closed as above.

| Variable | Fill in |
| --- | --- |
| `JEV_BASE_URL` | The treg server, for example `https://treg.to`. |
| `JEV_API_KEY` | Your treg token. It is sent as the `X-Treg-Token` header. |
| `JEV_TOOL` | The treg endpoint that reaches Jev, for example `openrouter.ai-judge.decide`. |
| `JEV_MODEL` | Optional. The Jev model, default `typesafe/jev-1.13`. |
| `JEV_PROVIDER` | Optional. `llm` sends the checks to the default model instead of Jev (below); unset or anything else is Jev. |

- **Demo provider (`JEV_PROVIDER=llm`):** for a demo on a free OpenRouter model (`ANTHROPIC_BASE_URL`, see "Calling Claude"), where treg is not set up. Every question one function would ask Jev goes to the default model in one `llm.call` (purpose `jev`, `_ask_model()`): all checks of all sentences of the message, as numbered items, answered as a JSON object of `true`/`false`. A failed call, a reply that is not that object, or a verdict that is missing or not a boolean makes the whole function fail closed, as above. The three `JEV_*` connection variables are not needed then. It is weaker than Jev: the same model writes the drafts, and a free model is a rougher classifier. Not for real users.

- The request is `POST {JEV_BASE_URL}/call/{JEV_TOOL}` with one question of type `noul`; the answer is read from `answers.q1.noul` (a probability; 0.5 or more is yes). This shape is copied from treg's `jev-memory` example and has not been run against the real service: confirm it with one real call before relying on the checks.
- **Cost and cap:** every function but `ask()` takes `db` and `user_id` first, because Jev is paid from the user's AI budget (see "Calling Claude"). Each function records its calls as one row in `llm_calls` (purpose `jev`, cost = calls times `jev.PRICE_USD`). `PRICE_USD` is a guess written by hand: confirm it against what treg charges. While the month's spend is at the cap Jev is not called and every check fails closed as above. So at the cap each new message from a match hands its card over, and those cards stay paused until the user answers or hands back. Never call `ask()` directly from a feature: the call would be neither capped nor recorded.
- Tests never reach Jev: the autouse `jev` fixture in `tests/conftest.py` replaces `ask()`. It answers no unless the sentence contains a phrase you list, `jev.yes["logistics"] = ["saturday"]`; `jev.asked` records each call.
