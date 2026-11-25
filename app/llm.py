"""The one place that calls Claude. Call it as `llm.complete(...)` so tests can replace it with a stub."""

import os
from dataclasses import dataclass

import anthropic

DEFAULT_MODEL = "claude-fable-5-2"


@dataclass
class Completion:
    text: str
    model: str
    # Token usage of this call, for working out what it cost.
    input_tokens: int
    output_tokens: int


def complete(system: str, prompt: str, max_tokens: int = 16000) -> Completion:
    """Send one prompt to Claude and return its text and token usage.

    The model is `ANTHROPIC_MODEL` (default `claude-fable-5-2`); the key is read from `ANTHROPIC_API_KEY`.
    """
    message = anthropic.Anthropic().messages.create(
        model=os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
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
