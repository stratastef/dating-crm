import hashlib
import logging
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import create_user
from app.push import send_push
from app.sms import send as real_sms_send  # the autouse `sms` fixture replaces `app.sms.send`

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


@pytest.fixture
def invite_code(database) -> str:
    """An invite code from the owner's CLI, printed the way the owner hands it out."""
    printed = subprocess.run([sys.executable, "-m", "app.invite_codes"], check=True, capture_output=True, text=True)
    [code] = printed.stdout.split()
    return code


class StubTwilio:
    """Stands in for `app.sms.post`, the one function that calls Twilio. `sent` records each request's form data.

    `answer` is Twilio's `(status, json)`, or an exception to raise.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.answer: tuple[int, dict] | Exception = (201, {"status": "queued"})

    def __call__(self, url: str, auth: tuple[str, str], data: dict) -> tuple[int, dict]:
        self.sent.append({"url": url, "auth": auth, **data})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def code(self) -> str:
        return re.search(r"\b\d{6}\b", self.sent[-1]["Body"])[0]  # pyright: ignore[reportOptionalSubscript]


@pytest.fixture
def twilio(monkeypatch):
    """The real `app.sms.send`, set up for Twilio as in production, with Twilio itself stubbed."""
    monkeypatch.setattr("app.sms.send", real_sms_send)
    monkeypatch.setenv("SMS_PROVIDER", "twilio")
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC0123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "auth-token")
    monkeypatch.setenv("TWILIO_SENDER", "DatingCRM")
    stub = StubTwilio()
    monkeypatch.setattr("app.sms.post", stub)
    return stub


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


def test_a_new_phone_number_with_a_valid_invite_code_gets_an_account_on_sign_in(app, sms, clock, invite_code):
    device = TestClient(app)

    assert device.post("/sign-in/code", json={"phone": PHONE, "invite_code": invite_code}).status_code == 204
    signed_in = sign_in(device, sms.code(PHONE))

    assert signed_in.status_code == 200
    assert signed_in.json()["new_account"] is True
    assert TestClient(app, headers=bearer(signed_in.json()["token"])).get("/me").json() == {"email": None}
    # The account is this number's now: the next sign-in needs no invite code.
    assert send_code(device) == 204
    assert sign_in(device, sms.code(PHONE)).json()["new_account"] is False


def test_a_used_invite_code_is_refused_for_another_phone_number(app, sms, clock, invite_code):
    device = TestClient(app)
    device.post("/sign-in/code", json={"phone": PHONE, "invite_code": invite_code})
    assert sign_in(device, sms.code(PHONE)).status_code == 200

    refused = device.post("/sign-in/code", json={"phone": "+15555550199", "invite_code": invite_code})

    assert (refused.status_code, refused.json()) == (403, {"detail": "invite_code_invalid"})
    assert [to for to, _ in sms.sent] == [PHONE]


def test_an_unknown_invite_code_is_refused(app, sms, clock, invite_code):
    refused = TestClient(app).post("/sign-in/code", json={"phone": PHONE, "invite_code": "AAAA-AAAA"})

    assert (refused.status_code, refused.json()) == (403, {"detail": "invite_code_invalid"})
    assert sms.sent == []


def test_an_invite_code_creates_one_account_even_when_two_numbers_got_a_sign_in_code_with_it(app, sms, clock, invite_code):
    device, second = TestClient(app), "+15555550199"
    for phone in [PHONE, second]:
        assert device.post("/sign-in/code", json={"phone": phone, "invite_code": invite_code}).status_code == 204
    assert sign_in(device, sms.code(PHONE)).status_code == 200

    refused = sign_in(device, sms.code(second), phone=second)

    assert (refused.status_code, refused.json()) == (403, {"detail": "invite_code_invalid"})


def test_an_invite_code_is_typed_without_regard_to_case_spaces_or_dashes(app, sms, clock, invite_code):
    typed = " " + invite_code.replace("-", " ").lower()

    assert TestClient(app).post("/sign-in/code", json={"phone": PHONE, "invite_code": typed}).status_code == 204


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


def test_a_sign_in_code_is_texted_through_twilio_from_the_dating_crm_sender(app, account, clock, twilio):
    device = TestClient(app)

    assert send_code(device) == 204

    [sent] = twilio.sent
    assert sent["url"] == "https://api.twilio.com/2010-04-01/Accounts/AC0123/Messages.json"
    assert sent["auth"] == ("AC0123", "auth-token")
    assert (sent["To"], sent["From"]) == (PHONE, "DatingCRM")
    assert "is your Dating CRM code" in sent["Body"]
    assert sign_in(device, twilio.code()).status_code == 200


def test_a_messaging_service_picks_the_sender_for_each_country(app, account, clock, twilio, monkeypatch):
    monkeypatch.setenv("TWILIO_SENDER", "MG0123")

    assert send_code(TestClient(app)) == 204

    assert twilio.sent[0]["MessagingServiceSid"] == "MG0123"
    assert "From" not in twilio.sent[0]


@pytest.mark.parametrize(
    "answer",
    [(400, {"code": 21408, "message": "Permission to send an SMS has not been enabled"}), httpx.ConnectTimeout("timed out")],
    ids=["refused", "unreachable"],
)
def test_when_twilio_fails_the_code_request_fails_and_no_sign_in_code_works(app, account, clock, twilio, answer):
    device = TestClient(app)
    assert send_code(device) == 204
    earlier = twilio.code()
    twilio.answer = answer

    failed = device.post("/sign-in/code", json={"phone": PHONE})

    assert (failed.status_code, failed.json()) == (503, {"detail": "sms_not_sent"})
    assert sign_in(device, twilio.code()).status_code == 410
    assert sign_in(device, earlier).status_code == 410


@pytest.mark.parametrize("setting, value", [("TWILIO_AUTH_TOKEN", ""), ("SMS_PROVIDER", "seven")])
def test_with_sms_provider_set_a_missing_twilio_setting_fails_the_code_request(app, account, clock, twilio, monkeypatch, setting, value):
    monkeypatch.setenv(setting, value)

    failed = TestClient(app).post("/sign-in/code", json={"phone": PHONE})

    assert (failed.status_code, failed.json()) == (503, {"detail": "sms_not_sent"})
    assert twilio.sent == []


def test_without_sms_provider_the_code_request_fails_closed(app, account, clock, twilio, monkeypatch, caplog):
    """A server set up without a provider writes no code to its log: a missing setting fails closed (#50)."""
    monkeypatch.delenv("SMS_PROVIDER")

    with caplog.at_level(logging.WARNING, logger="app.sms"):
        failed = TestClient(app).post("/sign-in/code", json={"phone": PHONE})

    assert (failed.status_code, failed.json()) == (503, {"detail": "sms_not_sent"})
    assert twilio.sent == []
    assert not re.findall(r"\b\d{6}\b", caplog.text)


def test_with_sms_provider_log_the_code_goes_to_the_server_log_and_not_to_twilio(app, account, clock, twilio, monkeypatch, caplog):
    monkeypatch.setenv("SMS_PROVIDER", "log")
    device = TestClient(app)

    with caplog.at_level(logging.WARNING, logger="app.sms"):
        assert send_code(device) == 204

    assert twilio.sent == []
    [logged] = re.findall(r"\b(\d{6}) is your Dating CRM code", caplog.text)
    assert sign_in(device, logged).status_code == 200


def test_a_number_listed_for_the_fixed_code_signs_in_with_it_and_gets_no_text(app, account, sms, monkeypatch):
    monkeypatch.setenv("SIGN_IN_FIXED_CODE", "222222")
    monkeypatch.setenv("SIGN_IN_FIXED_CODE_PHONES", f"+15555550199, {PHONE}")
    device = TestClient(app)

    assert device.post("/sign-in/code", json={"phone": PHONE}).status_code == 204

    assert sms.sent == []
    assert device.post("/sign-in", json={"phone": PHONE, "code": "222222"}).status_code == 200


def test_the_fixed_code_never_works_for_a_number_not_listed(app, account, sms, monkeypatch):
    monkeypatch.setenv("SIGN_IN_FIXED_CODE", "222222")
    monkeypatch.setenv("SIGN_IN_FIXED_CODE_PHONES", "+15555550199")
    device = TestClient(app)

    assert device.post("/sign-in/code", json={"phone": PHONE}).status_code == 204

    assert sms.code(PHONE) != "222222" or pytest.skip("the random code happened to be 222222")
    assert device.post("/sign-in", json={"phone": PHONE, "code": "222222"}).status_code == 401
