"""Session token vault: dating-app session tokens, encrypted at rest.

Each user has their own data key. It is stored wrapped (encrypted) by the master key,
which is read from `TOKEN_VAULT_MASTER_KEY` and never stored in the database.
Generate a master key with:
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

Never log a token. This module logs nothing.
"""

import os

from cryptography.fernet import Fernet
from sqlalchemy import Connection, text


def _master() -> Fernet:
    return Fernet(os.environ["TOKEN_VAULT_MASTER_KEY"])


def _user_key(db: Connection, user_id: int, create: bool = False) -> Fernet | None:
    if create:
        # ON CONFLICT keeps the existing key when two requests race to create it.
        db.execute(
            text("INSERT INTO vault_keys (user_id, wrapped_key) VALUES (:user_id, :wrapped_key) ON CONFLICT (user_id) DO NOTHING"),
            {"user_id": user_id, "wrapped_key": _master().encrypt(Fernet.generate_key()).decode()},
        )
    wrapped = db.execute(
        text("SELECT wrapped_key FROM vault_keys WHERE user_id = :user_id"), {"user_id": user_id}
    ).scalar_one_or_none()
    return wrapped and Fernet(_master().decrypt(wrapped.encode()))


def store_token(db: Connection, user_id: int, app: str, token: str) -> None:
    """Store the user's session token for a dating app, replacing any previous one."""
    db.execute(
        text(
            "INSERT INTO session_tokens (user_id, app, ciphertext) VALUES (:user_id, :app, :ciphertext) "
            "ON CONFLICT (user_id, app) DO UPDATE SET ciphertext = EXCLUDED.ciphertext"
        ),
        {"user_id": user_id, "app": app, "ciphertext": _user_key(db, user_id, create=True).encrypt(token.encode()).decode()},
    )


def read_token(db: Connection, user_id: int, app: str) -> str | None:
    """Return the user's session token for a dating app, or None if there is none."""
    ciphertext = db.execute(
        text("SELECT ciphertext FROM session_tokens WHERE user_id = :user_id AND app = :app"),
        {"user_id": user_id, "app": app},
    ).scalar_one_or_none()
    return ciphertext and _user_key(db, user_id).decrypt(ciphertext.encode()).decode()


def delete_token(db: Connection, user_id: int, app: str) -> None:
    db.execute(
        text("DELETE FROM session_tokens WHERE user_id = :user_id AND app = :app"),
        {"user_id": user_id, "app": app},
    )
