import hashlib
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import create_user
from app.push import send_push

PHONE = "+15555550100"


@pytest.fixture
def account(app):
    """An account with a phone number, for a user who signs in by SMS."""
    with app.state.engine.begin() as db:
        create_user(db, "owner@example.com", phone=PHONE)


@pytest.fixture
def clock(monkeypatch):
    """`clock.move(minutes=11)` moves the time sign-in codes are checked against."""

    class Clock:
        at = datetime.now(UTC)

        def move(self, **delta) -> None:
            self.at += timedelta(**delta)

    clock = Clock()
    monkeypatch.setattr("app.sign_in.now", lambda: clock.at)
    return clock


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def send_code(device: TestClient, phone: str = PHONE) -> int:
    return device.post("/sign-in/code", json={"phone": phone}).status_code


def sign_in(device: TestClient, code: str, phone: str = PHONE):
    return device.post("/sign-in", json={"phone": phone, "code": code})


def signed_in_device(app, sms) -> TestClient:
    device = TestClient(app)
    send_code(device)
    return TestClient(app, headers=bearer(sign_in(device, sms.code(PHONE)).json()["token"]))


def wrong(code: str) -> str:
    return f"{(int(code) + 1) % 10**6:06d}"


def test_a_returning_user_signs_in_with_the_code_texted_to_their_phone(app, account, sms):
    device = TestClient(app)

    assert device.post("/sign-in/code", json={"phone": PHONE}).status_code == 204
    [(to, body)] = sms.sent
    assert to == PHONE
    assert "your Dating CRM code" in body

    signed_in = device.post("/sign-in", json={"phone": PHONE, "code": sms.code(PHONE)})

    assert signed_in.status_code == 200
    assert TestClient(app, headers=bearer(signed_in.json()["token"])).get("/me").json() == {"email": "owner@example.com"}


def test_a_sign_in_code_expires_after_10_minutes(app, account, sms, clock):
    device = TestClient(app)
    send_code(device)
    clock.move(minutes=9, seconds=59)
    assert sign_in(device, sms.code(PHONE)).status_code == 200

    send_code(device)
    clock.move(minutes=10)
    expired = sign_in(device, sms.code(PHONE))

    assert (expired.status_code, expired.json()) == (410, {"detail": "code_expired"})


def test_the_sixth_try_on_one_sign_in_code_is_refused(app, account, sms, clock):
    device = TestClient(app)
    send_code(device)
    for _ in range(5):
        assert sign_in(device, wrong(sms.code(PHONE))).json() == {"detail": "wrong_code"}

    sixth = sign_in(device, sms.code(PHONE))

    assert (sixth.status_code, sixth.json()) == (429, {"detail": "too_many_tries"})


def test_a_sign_in_code_works_once(app, account, sms, clock):
    device = TestClient(app)
    send_code(device)
    assert sign_in(device, sms.code(PHONE)).status_code == 200

    assert sign_in(device, sms.code(PHONE)).status_code == 410


def test_a_new_sign_in_code_replaces_the_last(app, account, sms, clock):
    device = TestClient(app)
    send_code(device)
    first = sms.code(PHONE)
    send_code(device)
    assert sign_in(device, sms.code(PHONE)).status_code == 200

    assert sign_in(device, first).status_code == 410


def test_code_requests_beyond_the_limit_are_refused_per_phone_number(app, account, sms, clock):
    device = TestClient(app)
    with app.state.engine.begin() as db:
        create_user(db, None, phone="+15555550199")
    for _ in range(5):
        assert send_code(device) == 204

    refused = device.post("/sign-in/code", json={"phone": PHONE})

    assert (refused.status_code, refused.json()) == (429, {"detail": "too_many_requests"})
    assert len(sms.sent) == 5
    assert send_code(device, "+15555550199") == 204  # another number from the same address
    clock.move(hours=1)
    assert send_code(device) == 204


def test_code_requests_beyond_the_limit_are_refused_per_ip_address(app, account, clock):
    device = TestClient(app, client=("203.0.113.7", 50000))
    # Requests for numbers without an account count too, so nobody can probe numbers for free.
    for n in range(20):
        assert send_code(device, f"+1555555{n:04d}") == 403

    assert send_code(device) == 429
    assert send_code(TestClient(app, client=("198.51.100.9", 50000))) == 204


def test_a_phone_number_with_no_account_needs_an_invite_code(app, sms, clock):
    refused = TestClient(app).post("/sign-in/code", json={"phone": PHONE})

    assert (refused.status_code, refused.json()) == (403, {"detail": "invite_code_needed"})
    assert sms.sent == []


def test_a_phone_number_must_be_in_e164_form(app, account, sms):
    for phone in ["5555550100", "+1 555 555 0100", "+0555550100", "+1"]:
        assert TestClient(app).post("/sign-in/code", json={"phone": phone}).status_code == 422
    assert sms.sent == []


def test_signing_in_on_two_devices_gives_two_tokens_and_signing_out_on_one_leaves_the_other(app, account, sms, clock):
    phone, tablet = signed_in_device(app, sms), signed_in_device(app, sms)
    assert phone.headers["Authorization"] != tablet.headers["Authorization"]

    assert phone.post("/sign-out").status_code == 204

    assert phone.get("/me").status_code == 401
    assert tablet.get("/me").status_code == 200


def test_after_sign_out_that_device_gets_no_more_pushes(app, account, sms, clock, apns):
    phone, tablet = signed_in_device(app, sms), signed_in_device(app, sms)
    phone.post("/devices", json={"token": "aa11"})
    tablet.post("/devices", json={"token": "bb22"})

    phone.post("/sign-out")

    with app.state.engine.begin() as db:
        user_id = db.execute(text("SELECT id FROM users WHERE phone = :phone"), {"phone": PHONE}).scalar_one()
        send_push(db, user_id, "Hot lead", "Ada replied")
    assert [sent["url"] for sent in apns.sent] == ["https://api.push.apple.com/3/device/bb22"]


def alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], check=True)


def test_a_v1_token_still_authenticates_after_the_migration(app):
    alembic("downgrade", "t48_phone_sign_in-1")  # v1: one token per user, on the users table
    try:
        with app.state.engine.begin() as db:
            db.execute(
                text("INSERT INTO users (email, token_hash) VALUES ('owner@example.com', :token_hash)"),
                {"token_hash": hashlib.sha256(b"v1-token").hexdigest()},
            )
    finally:
        alembic("upgrade", "head")

    assert TestClient(app, headers=bearer("v1-token")).get("/me").json() == {"email": "owner@example.com"}


def test_the_cli_gives_an_account_a_phone_number_that_can_then_sign_in(app, client, sms, clock):
    subprocess.run([sys.executable, "-m", "app.sign_in", "user@example.com", PHONE], check=True)

    assert signed_in_device(app, sms).get("/me").json() == {"email": "user@example.com"}
