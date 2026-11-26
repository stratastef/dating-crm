"""Text messages to phones. `send()` is the only function that texts one; tests replace it."""

import logging

log = logging.getLogger(__name__)


def send(phone: str, body: str) -> None:
    """Text `body` to `phone` (E.164)."""
    # shortcut: no SMS provider yet, so the text goes to the server log for local development. #50 adds one.
    log.warning("SMS to %s: %s", phone, body)
