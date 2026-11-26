"""Invite codes: one-time codes that let one person create an account (ADR 0006).

The owner creates them for people on the waitlist; this prints them, one per line: `python -m app.invite_codes [count]`.
Only a SHA-256 of each code is stored, so a printed code cannot be shown again.
"""

import hashlib
import re
import secrets
import sys

from sqlalchemy import create_engine, text

from app.db import database_url

ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0, O, 1, I or L, which are easy to misread


def code_hash(code: str) -> str:
    # Case, spaces and dashes do not matter when a code is typed.
    return hashlib.sha256(re.sub(r"[^A-Z0-9]", "", code.upper()).encode()).hexdigest()


if __name__ == "__main__":
    codes = ["".join(secrets.choice(ALPHABET) for _ in range(8)) for _ in range(int(sys.argv[1]) if sys.argv[1:] else 1)]
    with create_engine(database_url()).begin() as connection:
        connection.execute(
            text("INSERT INTO invite_codes (code_hash) VALUES (:code_hash)"), [{"code_hash": code_hash(code)} for code in codes]
        )
    print(*(f"{code[:4]}-{code[4:]}" for code in codes), sep="\n")
