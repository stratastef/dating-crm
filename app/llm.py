"""The one place that calls Claude. Features call `llm.call(...)`, which records what each call cost."""

import os
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import anthropic
from sqlalchemy import Connection, text

DEFAULT_MODEL = "claude-fable-5-2"

# USD per million tokens: (input, output). Confirm these against Anthropic's price list before relying
# on the recorded costs; they are copied by hand and go stale when prices change.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-fable-5-2": (Decimal("8"), Decimal("40")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}


@dataclass
class Completion:
    text: str
    model: str
    # Token usage of this call, for working out what it cost.
    input_tokens: int
    output_tokens: int


def complete(system: str, prompt: str, max_tokens: int = 16000, images: Sequence[str] = ()) -> Completion:
    """Send one prompt to Claude and return its text and token usage. `images` are URLs Claude fetches and sees.

    The model is `ANTHROPIC_MODEL` (default `claude-fable-5-2`); the key is read from `ANTHROPIC_API_KEY`.
    """
    message = anthropic.Anthropic().messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [
                    *({"type": "image", "source": {"type": "url", "url": url}} for url in images),
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    if message.stop_reason == "refusal":
        # A refusal carries no usable text. Raising lets a job retry and then fail visibly.
        raise RuntimeError("Claude declined the request")
    return Completion(
        text="".join(block.text for block in message.content if block.type == "text"),
        model=message.model,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )


def call(
    db: Connection,
    user_id: int,
    purpose: str,
    system: str,
    prompt: str,
    max_tokens: int = 16000,
    images: Sequence[str] = (),
) -> Completion:
    """Send one prompt to Claude for a user and record what the call cost. Every feature calls Claude through this.

    `purpose` names the feature, for example `draft`. `images` are URLs of images to show Claude. The cost row is written in the caller's transaction.
    """
    # `complete` is looked up at call time so tests can replace it with a stub.
    completion = complete(system, prompt, max_tokens, images)
    # A model missing from the table is charged at the default model's price, so its cost is never zero.
    # shortcut: cache reads and writes are not priced apart, add them when a caller turns on prompt caching.
    input_price, output_price = PRICES.get(completion.model, PRICES[DEFAULT_MODEL])
    cost = (completion.input_tokens * input_price + completion.output_tokens * output_price) / 1_000_000
    # shortcut: if the caller's transaction rolls back (a job that fails after the call), the cost row is
    # lost with it. Write it in its own transaction if the budget cap needs failed attempts counted.
    db.execute(
        text(
            """
            INSERT INTO llm_calls (user_id, purpose, model, input_tokens, output_tokens, cost_usd)
            VALUES (:user_id, :purpose, :model, :input_tokens, :output_tokens, :cost)
            """
        ),
        {
            "user_id": user_id,
            "purpose": purpose,
            "model": completion.model,
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "cost": cost,
        },
    )
    return completion


def spend(db: Connection, user_id: int) -> Decimal:
    """What the user's recorded Claude calls cost in total, in USD."""
    return db.execute(
        text("SELECT coalesce(sum(cost_usd), 0) FROM llm_calls WHERE user_id = :user_id"), {"user_id": user_id}
    ).scalar_one()
