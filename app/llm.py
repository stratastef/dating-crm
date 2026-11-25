"""The one place that calls Claude. Features call `llm.call(...)`, which records what each call cost."""

import base64
import os
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

import anthropic
from sqlalchemy import Connection, text

from app.push import send_push

DEFAULT_MODEL = "claude-fable-5-2"

# USD per million tokens: (input, output). Confirm these against Anthropic's price list before relying
# on the recorded costs; they are copied by hand and go stale when prices change.
PRICES: dict[str, tuple[Decimal, Decimal]] = {
    "claude-fable-5-2": (Decimal("8"), Decimal("40")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
}


class BudgetReached(RuntimeError):
    """The user's Claude spend this month is at their cap: no call is made."""


@dataclass
class Completion:
    text: str
    model: str
    # Token usage of this call, for working out what it cost.
    input_tokens: int
    output_tokens: int


# One image for Claude to look at: a URL Claude fetches, or a file held here as (content type, bytes) with
# content type `image/jpeg` or `image/png`.
ImageInput = str | tuple[str, bytes]


def _image_source(image: ImageInput) -> dict:
    if isinstance(image, str):
        return {"type": "url", "url": image}
    media_type, data = image
    return {"type": "base64", "media_type": media_type, "data": base64.b64encode(data).decode()}


def complete(system: str, prompt: str, max_tokens: int = 16000, images: Sequence[ImageInput] = ()) -> Completion:
    """Send one prompt to Claude and return its text and token usage.

    The model is `ANTHROPIC_MODEL` (default `claude-fable-5-2`); the key is read from `ANTHROPIC_API_KEY`.
    `images` are URLs Claude fetches or `(content type, bytes)` pairs; Claude sees them before the prompt, in
    the order given.
    """
    message = anthropic.Anthropic().messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [
                    *({"type": "image", "source": _image_source(image)} for image in images),
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
    images: Sequence[ImageInput] = (),
) -> Completion:
    """Send one prompt to Claude for a user and record what the call cost. Every feature calls Claude through this.

    `purpose` names the feature, for example `draft`. `images` are images to show Claude: each a URL, or a
    `(content type, bytes)` pair for a file held here. Raises `BudgetReached`, without calling Claude, while the
    user's spend this month is at their cap. The call that reaches the cap sends the user a push.
    """
    # shortcut: two calls at the same moment can both pass this check, so spend can pass the cap by the cost
    # of the calls in flight. Lock the user row here if that ever matters.
    if budget_reached(db, user_id):
        raise BudgetReached("AI budget reached")
    # `complete` is looked up at call time so tests can replace it with a stub.
    completion = complete(system, prompt, max_tokens, images)
    # A model missing from the table is charged at the default model's price, so its cost is never zero.
    # shortcut: cache reads and writes are not priced apart, add them when a caller turns on prompt caching.
    input_price, output_price = PRICES.get(completion.model, PRICES[DEFAULT_MODEL])
    cost = (completion.input_tokens * input_price + completion.output_tokens * output_price) / 1_000_000
    # Own transaction: the money is spent even if the caller (a job handler) fails later and rolls back.
    with db.engine.begin() as own:
        own.execute(
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
        if budget_reached(own, user_id):  # spend was below the cap before this call, so the alert is sent once
            send_push(own, user_id, "AI budget reached", "Autopilot is paused until next month or a higher cap.")
    return completion


def spend(db: Connection, user_id: int) -> Decimal:
    """What the user's recorded Claude calls cost so far this calendar month (UTC), in USD."""
    return db.execute(
        text(
            "SELECT coalesce(sum(cost_usd), 0) FROM llm_calls WHERE user_id = :user_id"
            " AND created_at >= date_trunc('month', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
        ),
        {"user_id": user_id},
    ).scalar_one()


def cap(db: Connection, user_id: int) -> Decimal:
    """The user's hard cap on Claude spend per calendar month, in USD."""
    return db.execute(text("SELECT ai_budget_usd FROM users WHERE id = :id"), {"id": user_id}).scalar_one()


def budget_reached(db: Connection, user_id: int) -> bool:
    """True while this month's spend is at the cap: no Claude call is made and autopilot is paused."""
    return spend(db, user_id) >= cap(db, user_id)
