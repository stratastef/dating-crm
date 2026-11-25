import base64
import json
import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from sqlalchemy import text

from app.push import send_push


def unbase64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def user_id(app, email="user@example.com") -> int:
    with app.state.engine.begin() as db:
        return db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar_one()


def push(app, *args, **kwargs) -> None:
    with app.state.engine.begin() as db:
        send_push(db, *args, **kwargs)


def test_a_push_goes_to_each_device_the_user_registered(app, client, client_for, apns):
    assert client.post("/devices", json={"token": "aa11"}).status_code == 204
    client.post("/devices", json={"token": "bb22"})
    client.post("/devices", json={"token": "aa11"})  # the app registers again on every launch
    client_for("other@example.com").post("/devices", json={"token": "cc33"})

    push(app, user_id(app), "Hot lead", "Ada replied", card_id=7)

    assert sorted(sent["url"] for sent in apns.sent) == [
        "https://api.push.apple.com/3/device/aa11",
        "https://api.push.apple.com/3/device/bb22",
    ]
    assert apns.sent[0]["payload"] == {
        "aps": {"alert": {"title": "Hot lead", "body": "Ada replied"}, "sound": "default"},
        "card_id": 7,
    }


def test_a_push_is_signed_with_the_apns_key_for_the_apps_bundle(app, client, apns):
    client.post("/devices", json={"token": "aa11"})

    push(app, user_id(app), "Hot lead", "Ada replied")

    headers = apns.sent[0]["headers"]
    assert headers["apns-topic"] == "com.datingcrm.app"
    assert headers["apns-push-type"] == "alert"
    scheme, jwt = headers["authorization"].split(" ")
    assert scheme == "bearer"
    header, claims, signature = jwt.split(".")
    assert json.loads(unbase64(header)) == {"alg": "ES256", "kid": "KEY1234567"}
    assert json.loads(unbase64(claims))["iss"] == "TEAM123456"
    raw = unbase64(signature)  # r and s, 32 bytes each; verify() raises if the key did not sign it
    apns.key.public_key().verify(
        encode_dss_signature(int.from_bytes(raw[:32]), int.from_bytes(raw[32:])),
        f"{header}.{claims}".encode(),
        ec.ECDSA(hashes.SHA256()),
    )
    assert "card_id" not in apns.sent[0]["payload"]


def test_a_development_build_is_reached_through_the_sandbox(app, client, apns, monkeypatch):
    monkeypatch.setenv("APNS_SANDBOX", "1")
    client.post("/devices", json={"token": "aa11"})

    push(app, user_id(app), "Hot lead", "Ada replied")

    assert apns.sent[0]["url"] == "https://api.sandbox.push.apple.com/3/device/aa11"


def test_a_device_token_apple_calls_invalid_is_removed(app, client, apns):
    for token in ("aa11", "bb22", "cc33", "dd44"):
        client.post("/devices", json={"token": token})
    apns.answers = {
        "aa11": (410, "Unregistered"),  # the app was deleted from the phone
        "bb22": (400, "BadDeviceToken"),
        "cc33": (503, "ServiceUnavailable"),  # Apple's fault, not the token's
    }

    push(app, user_id(app), "Hot lead", "Ada replied")
    assert len(apns.sent) == 4  # one bad device does not stop the rest
    push(app, user_id(app), "Hot lead", "Ada replied again")

    assert [sent["url"].rsplit("/", 1)[-1] for sent in apns.sent[4:]] == ["cc33", "dd44"]


def test_without_apns_settings_a_push_is_logged_and_not_sent(app, client, apns, monkeypatch, caplog):
    monkeypatch.delenv("APNS_KEY")
    client.post("/devices", json={"token": "aa11"})

    with caplog.at_level(logging.INFO):
        push(app, user_id(app), "Hot lead", "Ada replied")

    assert apns.sent == []
    assert "APNS_KEY" in caplog.text


def test_a_device_token_must_be_hex(client):
    assert client.post("/devices", json={"token": "../../evil"}).status_code == 422
