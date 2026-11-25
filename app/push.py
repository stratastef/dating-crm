"""Push notifications to the user's iPhones through APNs.

Other code calls `send_push()`. `post()` is the only function that talks to Apple; tests replace it.
"""

import base64
import json
import logging
import os
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db

router = APIRouter()
log = logging.getLogger(__name__)


class Device(BaseModel):
    # The APNs device token, in hex. It becomes part of the APNs URL, so nothing else is accepted.
    token: str = Field(pattern=r"^[0-9a-fA-F]+$", max_length=200)


@router.post("/devices", status_code=204)
def register_device(device: Device, user: CurrentUser, db: Db) -> None:
    # A phone belongs to whoever signed in on it last.
    db.execute(
        text(
            "INSERT INTO devices (user_id, token) VALUES (:user_id, :token) "
            "ON CONFLICT (token) DO UPDATE SET user_id = EXCLUDED.user_id"
        ),
        {"user_id": user.id, "token": device.token},
    )


def post(url: str, headers: dict, payload: dict) -> tuple[int, str]:
    """Send one request to APNs and return its status and, on an error, Apple's reason."""
    # APNs accepts HTTP/2 only.
    with httpx.Client(http2=True, timeout=10) as client:
        response = client.post(url, headers=headers, json=payload)
    return response.status_code, response.json().get("reason", "") if response.content else ""


def _base64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


# (key, key ID, team ID, issued at, token). Apple rejects a token older than an hour and
# throttles keys that issue a new one more than once in 20 minutes, so one is reused for 40.
_provider_token: tuple[str, str, str, float, str] | None = None


def _authorization(key: str, key_id: str, team_id: str) -> str:
    """The provider token APNs wants: a JWT signed with the .p8 key (ES256)."""
    global _provider_token
    now = time.time()
    if not _provider_token or _provider_token[:3] != (key, key_id, team_id) or now - _provider_token[3] > 40 * 60:
        # A .env file cannot hold line breaks, so the key may be written with `\n` in their place.
        private_key = serialization.load_pem_private_key(key.replace("\\n", "\n").encode(), password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("APNS_KEY must be an elliptic-curve private key (the .p8 file from Apple)")
        signed = ".".join(
            _base64(json.dumps(part).encode())
            for part in ({"alg": "ES256", "kid": key_id}, {"iss": team_id, "iat": int(now)})
        )
        r, s = decode_dss_signature(private_key.sign(signed.encode(), ec.ECDSA(hashes.SHA256())))
        token = f"{signed}.{_base64(r.to_bytes(32) + s.to_bytes(32))}"
        _provider_token = (key, key_id, team_id, now, token)
    return f"bearer {_provider_token[4]}"


def send_push(db: Connection, user_id: int, title: str, body: str, card_id: int | None = None) -> None:
    """Send a notification to every device the user registered. Tapping it opens the card, if one is given."""
    names = ("APNS_KEY", "APNS_KEY_ID", "APNS_TEAM_ID", "APNS_BUNDLE_ID")
    key, key_id, team_id, bundle_id = (os.environ.get(name) for name in names)
    if not (key and key_id and team_id and bundle_id):
        # The title and body can quote a match's message, so they are not logged.
        log.info("Push for user %s not sent: set %s to send pushes", user_id, ", ".join(names))
        return
    headers = {
        "authorization": _authorization(key, key_id, team_id),
        "apns-topic": bundle_id,
        "apns-push-type": "alert",
    }
    payload: dict = {"aps": {"alert": {"title": title, "body": body}, "sound": "default"}}
    if card_id is not None:
        payload["card_id"] = card_id
    # A build run from Xcode gets a sandbox device token; TestFlight and App Store builds do not.
    host = "api.sandbox.push.apple.com" if os.environ.get("APNS_SANDBOX") else "api.push.apple.com"
    tokens = db.execute(
        text("SELECT token FROM devices WHERE user_id = :user_id ORDER BY id"), {"user_id": user_id}
    ).scalars().all()
    for token in tokens:
        try:
            status, reason = post(f"https://{host}/3/device/{token}", headers, payload)
        except httpx.HTTPError as error:
            # A push is best effort: an unreachable Apple must not fail the job that sends it.
            log.warning("Push for user %s failed: %r", user_id, error)
            continue
        if status == 410 or reason == "BadDeviceToken":
            # Apple no longer knows the token: the app was deleted, or the token was never valid.
            db.execute(text("DELETE FROM devices WHERE token = :token"), {"token": token})
        elif status != 200:
            log.warning("Push for user %s refused by APNs: %s %s", user_id, status, reason)
