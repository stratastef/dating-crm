"""Preferences: what the user wants, in plain words plus must-have and dealbreaker lists. Every save is a new version."""

import json
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import Connection, text

from app.auth import CurrentUser, Db

router = APIRouter()


class Preferences(BaseModel):
    wishes: str = ""
    must_haves: list[str] = []
    dealbreakers: list[str] = []


class PreferencesVersion(Preferences):
    version: int = 0  # 0 until the user saves for the first time


def current_preferences(db: Connection, user_id: int) -> PreferencesVersion:
    """The version in force for one user; version 0 and empty until they save one."""
    row = db.execute(
        text(
            "SELECT version, wishes, must_haves, dealbreakers FROM preferences"
            " WHERE user_id = :user_id ORDER BY version DESC LIMIT 1"
        ),
        {"user_id": user_id},
    ).one_or_none()
    return PreferencesVersion.model_validate(row, from_attributes=True) if row else PreferencesVersion()


@router.get("/preferences", response_model=PreferencesVersion)
def read(user: CurrentUser, db: Db):
    return current_preferences(db, user.id)


class DatedVersion(PreferencesVersion):
    created_at: datetime  # in force from this moment until the next version's


@router.get("/preferences/versions", response_model=list[DatedVersion])
def versions(user: CurrentUser, db: Db):
    """Every version the user saved, oldest first."""
    return db.execute(
        text(
            "SELECT version, wishes, must_haves, dealbreakers, created_at FROM preferences"
            " WHERE user_id = :user_id ORDER BY version"
        ),
        {"user_id": user.id},
    ).all()


@router.put("/preferences",response_model=PreferencesVersion)
def save(preferences: Preferences, user: CurrentUser, db: Db):
    """Store the preferences as the next version. Earlier versions are kept."""
    return db.execute(
        text(
            """
            INSERT INTO preferences (user_id, version, wishes, must_haves, dealbreakers)
            SELECT :user_id, COALESCE(MAX(version), 0) + 1, :wishes, CAST(:must_haves AS jsonb), CAST(:dealbreakers AS jsonb)
            FROM preferences WHERE user_id = :user_id
            RETURNING version, wishes, must_haves, dealbreakers
            """
        ),
        {
            "user_id": user.id,
            "wishes": preferences.wishes,
            "must_haves": json.dumps(preferences.must_haves),
            "dealbreakers": json.dumps(preferences.dealbreakers),
        },
    ).one()
