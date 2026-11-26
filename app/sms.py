"""Text messages to phones, through Twilio (ADR 0010).

`send()` is the only function that texts a phone, and `post()` the only one that talks to Twilio; tests replace them.
Without `SMS_PROVIDER`, the text goes to the server log instead (local development).
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

TWILIO_SETTINGS = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SENDER")


class NotSent(Exception):
    """The text did not reach the provider: a setting is missing, or Twilio refused it or could not be reached."""


def post(url: str, auth: tuple[str, str], data: dict[str, str]) -> tuple[int, dict]:
    """Send one request to Twilio and return its status and JSON answer."""
    with httpx.Client(timeout=10) as client:
        response = client.post(url, auth=auth, data=data)
    return response.status_code, response.json()


def send(phone: str, body: str) -> None:
    """Text `body` to `phone` (E.164). With `SMS_PROVIDER` set, raises `NotSent` unless Twilio accepted the text."""
    provider = os.environ.get("SMS_PROVIDER")
    if not provider:
        log.warning("SMS to %s: %s", phone, body)
        return
    account, token, sender = (os.environ.get(name) for name in TWILIO_SETTINGS)
    if provider != "twilio" or not (account and token and sender):
        raise NotSent(f"set SMS_PROVIDER=twilio and {', '.join(TWILIO_SETTINGS)}")
    # A Messaging Service (its SID starts with MG) picks the sender for each country; anything else is the sender.
    data = {"To": phone, "Body": body, ("MessagingServiceSid" if sender.startswith("MG") else "From"): sender}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json"
    try:
        status, answer = post(url, (account, token), data)
    except (httpx.HTTPError, ValueError) as error:  # ValueError: an answer that is not JSON
        raise NotSent(f"Twilio could not be reached: {error!r}") from error
    if status >= 300:
        raise NotSent(f"Twilio refused the text: {status} {answer.get('code')} {answer.get('message')}")
