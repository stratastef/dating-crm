"""Tombstones: what stays of a purged person, so that no sync stores them again.

A tombstone is a keyed hash of the app and the app's ID for the person. It holds no personal content, and
without the master key it cannot be matched to an ID.
"""

import hashlib
import hmac
import os
from typing import Literal

from sqlalchemy import Connection, text

# `match`: a card's `external_id`. `profile`: a swipe candidate's `profile_id`.
Kind = Literal["match", "profile"]


def _key(user_id: int, kind: Kind, app: str, external_id: str) -> str:
    # shortcut: keyed with the vault's master key, so a new master key forgets every tombstone. Give the
    # tombstones their own key if the master key is ever rotated.
    secret = os.environ["TOKEN_VAULT_MASTER_KEY"].encode()
    return hmac.new(secret, f"{user_id}\0{kind}\0{app}\0{external_id}".encode(), hashlib.sha256).hexdigest()


def bury(db: Connection, user_id: int, kind: Kind, app: str, external_id: str) -> None:
    """Remember that this person was purged. Call it in the transaction that deletes their rows."""
    db.execute(
        text("INSERT INTO purge_tombstones (user_id, key) VALUES (:user_id, :key) ON CONFLICT DO NOTHING"),
        {"user_id": user_id, "key": _key(user_id, kind, app, external_id)},
    )


def is_buried(db: Connection, user_id: int, kind: Kind, app: str, external_id: str) -> bool:
    """True if this person was purged. Every path that stores a match or a candidate must ask first."""
    return db.execute(
        text("SELECT EXISTS (SELECT 1 FROM purge_tombstones WHERE user_id = :user_id AND key = :key)"),
        {"user_id": user_id, "key": _key(user_id, kind, app, external_id)},
    ).scalar_one()
