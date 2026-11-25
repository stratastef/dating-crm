"""User settings: columns on the `users` row."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.auth import CurrentUser, Db

router = APIRouter()


class Settings(BaseModel):
    # Days without a message before a card is marked Stalled.
    stalled_after_days: int = Field(ge=1)


@router.get("/settings", response_model=Settings)
def read_settings(user: CurrentUser, db: Db):
    return db.execute(text("SELECT stalled_after_days FROM users WHERE id = :id"), {"id": user.id}).one()


@router.patch("/settings", response_model=Settings)
def update_settings(settings: Settings, user: CurrentUser, db: Db):
    return db.execute(
        text("UPDATE users SET stalled_after_days = :stalled_after_days WHERE id = :id RETURNING stalled_after_days"),
        {"id": user.id, **settings.model_dump()},
    ).one()
