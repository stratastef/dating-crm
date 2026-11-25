"""API authentication: one opaque bearer token per user.

The client sends `Authorization: Bearer <token>`. Only the SHA-256 of the token is stored.
Create a user and print their token once: `python -m app.auth <email>`.
"""

import hashlib
import secrets
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection, create_engine, text

from app.db import database_url


@dataclass(frozen=True)
class User:
    id: int
    email: str


def _hash(token: str) -> str:
    # Tokens are 256 random bits, so a fast unsalted hash is enough.
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(connection: Connection, email: str) -> str:
    """Insert a user and return their API token. The token cannot be recovered later."""
    token = secrets.token_urlsafe(32)
    connection.execute(
        text("INSERT INTO users (email, token_hash) VALUES (:email, :token_hash)"),
        {"email": email, "token_hash": _hash(token)},
    )
    return token


def _connection(request: Request) -> Iterator[Connection]:
    with request.app.state.engine.begin() as connection:
        yield connection


# One transaction per request, committed when the route returns.
Db = Annotated[Connection, Depends(_connection)]


def _current_user(
    db: Db,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))],
) -> User:
    row = credentials and db.execute(
        text("SELECT id, email FROM users WHERE token_hash = :token_hash"),
        {"token_hash": _hash(credentials.credentials)},
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="invalid or missing token", headers={"WWW-Authenticate": "Bearer"})
    return User(id=row.id, email=row.email)


# Declare `user: CurrentUser` in a route to require authentication and get the caller.
CurrentUser = Annotated[User, Depends(_current_user)]


if __name__ == "__main__":
    with create_engine(database_url()).begin() as connection:
        print(create_user(connection, sys.argv[1]))
