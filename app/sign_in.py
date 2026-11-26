"""Sign-in by phone number and a six-digit sign-in code sent by SMS (ADR 0006).

`POST /sign-in/code` texts a sign-in code, `POST /sign-in` trades it for an API token for this device, and
`POST /sign-out` revokes the caller's token. A phone number with no account needs an invite code (`app.invite_codes`):
the sign-in that uses it creates the account. Give an existing account a phone number:
`python -m app.sign_in <email> <phone>`.
"""

import hashlib
import hmac
import logging
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app import sms
from app.auth import CurrentUser, Db, create_user, issue_token
from app.db import database_url
from app.invite_codes import code_hash

router = APIRouter()
log = logging.getLogger(__name__)

E164 = r"^\+[1-9]\d{6,14}$"
CODE_MINUTES = 10  # a sign-in code is valid this long
MAX_TRIES = 5  # per sign-in code
PER_PHONE_PER_HOUR = 5  # code requests
PER_IP_PER_HOUR = 20  # code requests, refused ones included


def now() -> datetime:
    """The clock of sign-in codes. Tests move it."""
    return datetime.now(UTC)


class CodeRequest(BaseModel):
    phone: str = Field(pattern=E164)
    invite_code: str | None = None  # needed only by a phone number with no account


class SignIn(BaseModel):
    phone: str = Field(pattern=E164)
    code: str = Field(pattern=r"^\d{6}$")


def _refusal(status: int, detail: str) -> JSONResponse:
    # Returned, not raised: the request's transaction must still commit the try or request it counted.
    return JSONResponse(status_code=status, content={"detail": detail})


def _hash(phone: str, code: str) -> str:
    return hashlib.sha256(f"{phone} {code}".encode()).hexdigest()


@router.post("/sign-in/code", status_code=204, response_model=None)
def send_code(body: CodeRequest, request: Request, db: Db) -> JSONResponse | None:
    at = now()
    ip = request.client.host if request.client else ""
    by_phone, by_ip = db.execute(
        text(
            "SELECT count(*) FILTER (WHERE phone = :phone), count(*) FILTER (WHERE ip = :ip) FROM sign_in_codes"
            " WHERE created_at > :since"
        ),
        {"phone": body.phone, "ip": ip, "since": at - timedelta(hours=1)},
    ).one()
    if by_phone >= PER_PHONE_PER_HOUR or by_ip >= PER_IP_PER_HOUR:
        return _refusal(429, "too_many_requests")
    user_id = db.execute(text("SELECT id FROM users WHERE phone = :phone"), {"phone": body.phone}).scalar_one_or_none()
    invite_id = None
    if not user_id and body.invite_code:
        invite_id = db.execute(
            text("SELECT id FROM invite_codes WHERE code_hash = :code_hash AND used_at IS NULL"),
            {"code_hash": code_hash(body.invite_code)},
        ).scalar_one_or_none()
    code = f"{secrets.randbelow(10**6):06d}"
    # A phone number has one live code: a new one replaces the last.
    db.execute(text("UPDATE sign_in_codes SET code_hash = NULL WHERE phone = :phone"), {"phone": body.phone})
    db.execute(
        text(
            "INSERT INTO sign_in_codes (user_id, phone, ip, code_hash, invite_code_id, created_at)"
            " VALUES (:user_id, :phone, :ip, :code_hash, :invite_id, :at)"
        ),
        {
            "user_id": user_id,
            "phone": body.phone,
            "ip": ip,
            "code_hash": (user_id or invite_id) and _hash(body.phone, code),
            "invite_id": invite_id,
            "at": at,
        },
    )
    if not user_id and not invite_id:
        return _refusal(403, "invite_code_invalid" if body.invite_code else "invite_code_needed")
    try:
        sms.send(body.phone, f"{code} is your Dating CRM code. It expires in {CODE_MINUTES} minutes.")
    except sms.NotSent as error:
        log.warning("Sign-in code for %s not sent: %s", body.phone, error)
        # Fail closed: the request still counts towards the limits, but no code of this number works any more.
        db.execute(text("UPDATE sign_in_codes SET code_hash = NULL WHERE phone = :phone"), {"phone": body.phone})
        return _refusal(503, "sms_not_sent")


@router.post("/sign-in", response_model=None)
def sign_in(body: SignIn, db: Db) -> dict[str, str | bool] | JSONResponse:
    # One statement counts the try and reads the code, so two requests at once cannot share the last try.
    row = db.execute(
        text(
            "UPDATE sign_in_codes SET tries = tries + 1 WHERE id = ("
            " SELECT id FROM sign_in_codes WHERE phone = :phone AND code_hash IS NOT NULL ORDER BY id DESC LIMIT 1)"
            " RETURNING id, user_id, invite_code_id, code_hash, tries, created_at"
        ),
        {"phone": body.phone},
    ).one_or_none()
    if not row or row.created_at <= now() - timedelta(minutes=CODE_MINUTES):
        return _refusal(410, "code_expired")
    if row.tries > MAX_TRIES:
        return _refusal(429, "too_many_tries")
    if not hmac.compare_digest(row.code_hash, _hash(body.phone, body.code)):
        return _refusal(401, "wrong_code")
    db.execute(text("UPDATE sign_in_codes SET code_hash = NULL WHERE id = :id"), {"id": row.id})
    if row.user_id:
        return {"token": issue_token(db, row.user_id), "new_account": False}
    # The invite code is used up here, in one statement, so it creates one account even if two numbers got a code with it.
    used = db.execute(
        text("UPDATE invite_codes SET used_at = :at WHERE id = :id AND used_at IS NULL"), {"id": row.invite_code_id, "at": now()}
    )
    if not used.rowcount:
        return _refusal(403, "invite_code_invalid")
    return {"token": create_user(db, None, phone=body.phone), "new_account": True}


@router.post("/sign-out", status_code=204)
def sign_out(user: CurrentUser, db: Db) -> None:
    # The device's push registration goes with its token (ON DELETE CASCADE), so this phone gets no more pushes.
    db.execute(text("DELETE FROM api_tokens WHERE id = :id AND user_id = :user_id"), {"id": user.token_id, "user_id": user.id})


if __name__ == "__main__":
    email, phone = sys.argv[1:3]
    if not re.match(E164, phone):
        sys.exit("Write the phone number in E.164 form, such as +491701234567.")
    with create_engine(database_url()).begin() as connection:
        found = connection.execute(text("UPDATE users SET phone = :phone WHERE email = :email"), {"phone": phone, "email": email})
        if found.rowcount != 1:
            sys.exit(f"No account has the email {email}.")
