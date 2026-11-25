"""The AI budget: this month's Claude spend and the user's hard cap. The cap itself is enforced in `app/llm.py`."""

from decimal import Decimal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import llm
from app.auth import CurrentUser, Db

router = APIRouter()


class Cap(BaseModel):
    cap_usd: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


def budget(db: Connection, user_id: int) -> dict:
    # `paused` is true while the cap stops model calls and autopilot.
    return {
        "spend_usd": float(llm.spend(db, user_id)),
        "cap_usd": float(llm.cap(db, user_id)),
        "paused": llm.budget_reached(db, user_id),
    }


@router.get("/budget")
def read_budget(user: CurrentUser, db: Db) -> dict:
    return budget(db, user.id)


@router.put("/budget")
def set_cap(cap: Cap, user: CurrentUser, db: Db) -> dict:
    db.execute(text("UPDATE users SET ai_budget_usd = :cap WHERE id = :id"), {"cap": cap.cap_usd, "id": user.id})
    return budget(db, user.id)


def budget_reached_response(request, error: llm.BudgetReached) -> JSONResponse:
    """A route that needs Claude answers 402 at the cap. Registered in `app/main.py`."""
    return JSONResponse(status_code=402, content={"detail": str(error)})
