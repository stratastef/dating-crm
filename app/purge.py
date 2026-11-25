"""Find and purge: honor a match's request to have their data deleted."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.audit import record_action
from app.auth import CurrentUser, Db
from app.cards import _COLUMNS, Card

router = APIRouter()


@router.get("/people", response_model=list[Card])
def find_people(user: CurrentUser, db: Db, q: str = Query(min_length=1)):
    """The caller's cards, on any app, whose name or handle (`external_id`) contains `q`, ignoring case."""
    return db.execute(
        text(
            f"""
            SELECT {_COLUMNS} FROM cards
            WHERE user_id = :user_id
              AND (strpos(lower(name), lower(:q)) > 0 OR strpos(lower(coalesce(external_id, '')), lower(:q)) > 0)
            ORDER BY id
            """
        ),
        {"user_id": user.id, "q": q},
    ).all()


class Purge(BaseModel):
    # Every card of the person, as found with `GET /people`.
    card_ids: list[int] = Field(min_length=1)
    # The purge cannot be undone, so the caller must say it in so many words.
    confirm: Literal["purge"]


@router.post("/people/purge")
def purge_people(purge: Purge, user: CurrentUser, db: Db) -> dict[str, int]:
    """Delete the cards and everything stored about them, in the request's one transaction.

    Every table that references `cards` does so with ON DELETE CASCADE, so deleting the card deletes its rows.
    The `cards_purge_audit_log` trigger deletes the audit entries about the match.
    """
    card_ids = set(purge.card_ids)
    deleted = db.execute(
        text("DELETE FROM cards WHERE user_id = :user_id AND id = ANY(:ids) RETURNING id, app"),
        {"user_id": user.id, "ids": list(card_ids)},
    ).all()
    if len(deleted) != len(card_ids):
        # Raising rolls the transaction back: nothing is purged.
        raise HTTPException(status_code=404, detail="card not found")
    for card in deleted:
        # The entry names the card only by its id, which now points at nothing.
        record_action(db, user.id, type="purge", app=card.app, target=f"card:{card.id}", trigger="deletion request")
    return {"purged": len(deleted)}
