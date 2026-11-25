# Calling Claude

All Claude calls go through one function, `call()` in `app/llm.py`. It sends the prompt with the `anthropic` SDK (`complete()`) and records what the call cost. Never call `complete()` directly: the cost would not be recorded.

```python
from app import llm

result = llm.call(db, user.id, "draft", system="...", prompt="...")  # result.text, result.model, result.input_tokens, result.output_tokens
```

- To show Claude images, pass `images=[...]`. An item is an `https` URL that Claude fetches, or `("image/png", data)` (media type and bytes) to send the picture itself.

- The model is read from `ANTHROPIC_MODEL` (default `claude-fable-5-2`) and the key from `ANTHROPIC_API_KEY`. Compose passes both to the API and worker. A feature that needs another model passes `model=` to `call()`; cost and the cap apply the same way.
- Every call inserts one row in `llm_calls`: `purpose` (the third argument, naming the feature), `model`, both token counts and `cost_usd`. The row is written in its own transaction, so it is kept when the calling job fails. `llm.spend(db, user_id)` is the user's total for the current calendar month (UTC) in USD.
- **Other paid models:** Jev is paid from the same budget. `app/jev.py` asks `llm.budget_reached()` before it calls and adds its cost with `llm.record(db, user_id, purpose, model, cost)`. A new paid model must do both.
- **AI budget:** each user has a hard monthly cap, `users.ai_budget_usd`, default 50 USD. `GET /budget` returns `{"spend_usd", "cap_usd", "paused"}` and `PUT /budget` with `{"cap_usd": 20}` sets the cap (routes in `app/budget.py`). While the month's spend is at the cap, `call()` raises `llm.BudgetReached` without calling Claude (a route answers `402`; a job retries and then fails), and the worker skips autopilot jobs with the reason `AI budget reached`. The call that reaches the cap sends the user a push. The budget pause is computed, not a row in `autopilot_pauses`: a new month or a higher cap lifts it, `POST /autopilot/resume` does not, and it is not shown by `GET /autopilot/pause`. Pauses set for other reasons are untouched. Spend can pass the cap by the cost of calls already in flight.
- Cost is tokens times the per-model price in `llm.PRICES` (USD per million tokens). The prices are copied by hand: confirm them against Anthropic's price list. A model missing from the table is charged at the default model's price.
- A refusal raises `RuntimeError`. Server-side fallback models are not configured. Code that can go on without Claude catches `llm.Failed` (the budget cap, a refusal or an API error); only `app/llm.py` imports `anthropic`.
- Tests never reach the API: the autouse `llm` fixture in `tests/conftest.py` replaces `complete()` with a stub. Set `llm.reply` to choose the text and read `llm.prompts`, `llm.systems` and `llm.images` to see what was sent. For a route that calls Claude more than once, set `llm.replies` to a list; it is used up first, one per call.
