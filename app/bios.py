"""Bios: rewrites of the user's bio and prompt answers per dating app, and the version they accepted."""

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import text

from app import llm
from app.auth import CurrentUser, Db

router = APIRouter()


class Bio(BaseModel):
    bio: str = ""
    prompts: dict[str, str] = {}  # prompt -> answer


_SYSTEM = (
    "You rewrite one person's dating-app bio and prompt answers so they read like that person wrote them on a"
    " good day. Write in the voice the style profile describes. Keep every fact; invent none. Keep the same"
    " prompts and stay within the length limits of the named app. Reply with JSON only, in the shape"
    ' {"bio": "...", "prompts": {"<prompt>": "<answer>"}}.'
)


@router.post("/bios/{app}/rewrite", response_model=Bio)
def rewrite(app: str, current: Bio, user: CurrentUser, db: Db):
    """Rewrite the given bio and prompt answers for one app in the user's voice. Nothing is stored.

    To regenerate, call it again; send an edited rewrite to have that one rewritten.
    """
    profile = db.execute(
        text("SELECT profile FROM voice_profiles WHERE user_id = :user_id"), {"user_id": user.id}
    ).scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=409, detail="style profile not written yet")
    prompt = "\n".join(
        [
            f"<app>{app}</app>",
            f"<style_profile>\n{profile}\n</style_profile>",
            f"<bio>\n{current.bio}\n</bio>",
            "<prompts>",
            *(f"Q: {question}\nA: {answer}" for question, answer in current.prompts.items()),
            "</prompts>",
        ]
    )
    # shortcut: Claude is called inside the request, which holds a database connection meanwhile. Move
    # to a job if rewrites get slow or many users rewrite at once.
    # `llm.complete` is looked up on the module at call time so tests can replace it.
    reply = llm.complete(_SYSTEM, prompt).text
    try:
        return Bio.model_validate_json(reply)
    except ValidationError:
        raise HTTPException(status_code=502, detail="the rewrite was not usable, try again")


@router.put("/bios/{app}", response_model=Bio)
def accept(app: str, accepted: Bio, user: CurrentUser, db: Db):
    """Store the version the user accepted for one app, replacing the previous one."""
    return db.execute(
        text(
            """
            INSERT INTO bios (user_id, app, bio, prompts) VALUES (:user_id, :app, :bio, CAST(:prompts AS jsonb))
            ON CONFLICT (user_id, app)
            DO UPDATE SET bio = EXCLUDED.bio, prompts = EXCLUDED.prompts, updated_at = now()
            RETURNING bio, prompts
            """
        ),
        {"user_id": user.id, "app": app, "bio": accepted.bio, "prompts": json.dumps(accepted.prompts)},
    ).one()


@router.get("/bios/{app}", response_model=Bio)
def read(app: str, user: CurrentUser, db: Db):
    """The accepted version for one app; empty until the user has accepted one."""
    row = db.execute(
        text("SELECT bio, prompts FROM bios WHERE user_id = :user_id AND app = :app"), {"user_id": user.id, "app": app}
    ).one_or_none()
    return row or Bio()
