"""Find and purge: honor a match's request to have their data deleted."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import text

from app import calendar, swipes, tombstones
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


@router.get("/people/candidates", response_model=list[swipes.Candidate])
def find_candidates(user: CurrentUser, db: Db, q: str = Query(min_length=1)):
    """The caller's swipe candidates, on any app, whose name or profile ID contains `q`, ignoring case.

    A candidate is not a card: a person the user only swiped on is found here and not with `GET /people`.
    """
    return db.execute(
        text(
            f"""
            SELECT {swipes._COLUMNS} FROM swipe_candidates
            WHERE user_id = :user_id
              AND (strpos(lower(name), lower(:q)) > 0 OR strpos(lower(profile_id), lower(:q)) > 0)
            ORDER BY id
            """
        ),
        {"user_id": user.id, "q": q},
    ).all()


class Purge(BaseModel):
    # Every card of the person, as found with `GET /people`.
    card_ids: list[int] = []
    # Every swipe candidate of the person, as found with `GET /people/candidates`.
    candidate_ids: list[int] = []
    # The purge cannot be undone, so the caller must say it in so many words.
    confirm: Literal["purge"]

    @model_validator(mode="after")
    def _names_somebody(self):
        if not (self.card_ids or self.candidate_ids):
            raise ValueError("give at least one of card_ids and candidate_ids")
        return self


@router.post("/people/purge")
def purge_people(purge: Purge, user: CurrentUser, db: Db) -> dict[str, int]:
    """Delete the cards and swipe candidates and everything stored about them, in the request's one transaction.

    Every table that references `cards` does so with ON DELETE CASCADE, so deleting the card deletes its rows.
    The `cards_purge_audit_log` trigger deletes the audit entries about the match, and the
    `swipe_candidates_purge_audit_log` trigger those about a candidate.
    """
    params = {"user_id": user.id, "ids": list(set(purge.card_ids)), "candidate_ids": list(set(purge.candidate_ids))}
    cards = db.execute(
        text("SELECT id, app, external_id FROM cards WHERE user_id = :user_id AND id = ANY(:ids) FOR UPDATE"), params
    ).all()
    if len(cards) != len(params["ids"]):
        raise HTTPException(status_code=404, detail="card not found")
    candidates = db.execute(
        text(
            "SELECT id, app, profile_id FROM swipe_candidates"
            " WHERE user_id = :user_id AND id = ANY(:candidate_ids) FOR UPDATE"
        ),
        params,
    ).all()
    if len(candidates) != len(params["candidate_ids"]):
        raise HTTPException(status_code=404, detail="candidate not found")
    # The calendar events carry the match's name. They go first, while the holds still say which they are:
    # if Google fails, the transaction rolls back and the purge can be sent again.
    calendar.delete_events(db, user.id, params["ids"])
    # While the match or profile exists in the dating app, the next sync would store it again. The tombstone
    # stops that. A card without an `external_id` came from no app and needs none.
    for card in cards:
        if card.external_id:
            tombstones.bury(db, user.id, "match", card.app, card.external_id)
    for candidate in candidates:
        tombstones.bury(db, user.id, "profile", candidate.app, candidate.profile_id)
    db.execute(text("DELETE FROM cards WHERE user_id = :user_id AND id = ANY(:ids)"), params)
    db.execute(text("DELETE FROM swipe_candidates WHERE user_id = :user_id AND id = ANY(:candidate_ids)"), params)
    for kind, rows in (("card", cards), ("candidate", candidates)):
        for row in rows:
            # The entry names the card or candidate only by its id, which now points at nothing.
            record_action(
                db, user.id, type="purge", app=row.app, target=f"{kind}:{row.id}", trigger="deletion request"
            )
    return {"purged": len(cards) + len(candidates)}
