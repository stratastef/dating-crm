"""Sign-in by phone number and a six-digit sign-in code sent by SMS (ADR 0006).

`POST /sign-in/code` texts a sign-in code, `POST /sign-in` trades it for an API token for this device, and
`POST /sign-out` revokes the caller's token. Give an existing account a phone number:
`python -m app.sign_in <email> <phone>`.
"""

import hashlib
import hmac
import re
import secrets
import sys
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app import sms
from app.auth import CurrentUser, Db, issue_token
from app.db import database_url

router = APIRouter()

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
    code = f"{secrets.randbelow(10**6):06d}"
    # A phone number has one live code: a new one replaces the last.
    db.execute(text("UPDATE sign_in_codes SET code_hash = NULL WHERE phone = :phone"), {"phone": body.phone})
    db.execute(
        text(
            "INSERT INTO sign_in_codes (user_id, phone, ip, code_hash, created_at)"
            " VALUES (:user_id, :phone, :ip, :code_hash, :at)"
        ),
        {"user_id": user_id, "phone": body.phone, "ip": ip, "code_hash": user_id and _hash(body.phone, code), "at": at},
    )
    if not user_id:
        return _refusal(403, "invite_code_needed")
    sms.send(body.phone, f"{code} is your Dating CRM code. It expires in {CODE_MINUTES} minutes.")


@router.post("/sign-in", response_model=None)
def sign_in(body: SignIn, db: Db) -> dict[str, str] | JSONResponse:
    # One statement counts the try and reads the code, so two requests at once cannot share the last try.
    row = db.execute(
        text(
            "UPDATE sign_in_codes SET tries = tries + 1 WHERE id = ("
            " SELECT id FROM sign_in_codes WHERE phone = :phone AND code_hash IS NOT NULL ORDER BY id DESC LIMIT 1)"
            " RETURNING id, user_id, code_hash, tries, created_at"
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
    return {"token": issue_token(db, row.user_id)}


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
