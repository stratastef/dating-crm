"""Paid items: Super Likes, Roses and Boosts. The app proposes one, the user approves or declines it in the
review queue, and only an approved proposal is spent, once.

`spend()` is the only code that reaches a connector's paid capability. It spends an item the account already
holds; nothing here buys an item or touches a payment method.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import Connection, Row, text

from app.audit import record_action
from app.auth import CurrentUser, Db
from app.connectors import CapabilityFailed, CapabilityUnavailable, PaidItem, _run, disabled_capabilities

router = APIRouter()

_SELECT = (
    "SELECT p.id, p.app, p.item, COALESCE(c.name, p.app) AS name, p.reason, p.status, p.candidate_id,"
    " c.photos->>0 AS photo_url, p.cost, p.created_at"
    " FROM paid_item_proposals p LEFT JOIN swipe_candidates c ON c.id = p.candidate_id"
)
# A proposal for a profile waits only while the profile does: after a swipe there is nobody to spend it on.
_WAITS = "p.status = 'pending' AND (p.candidate_id IS NULL OR c.decision IS NULL)"


class Proposal(BaseModel):
    id: int
    app: str
    item: PaidItem
    name: str  # the profile the item is for; the app's name for an item spent on nobody (a Boost)
    reason: str
    status: str  # pending, declined, spent, or failed (approved, but the app did not spend it)
    candidate_id: int | None  # the swipe candidate the item is for, whose profile the app opens; null for a Boost
    photo_url: str | None  # the candidate's first photo; null for a Boost or a profile without photos
    cost: str | None  # what the item costs, as the dating app reported it ("$1.99"); null when it reported none


def _connectors() -> dict:
    from app.sync import CONNECTORS  # imported here: app.sync imports app.cards, which leads back to this module

    return CONNECTORS


class NotApproved(Exception):
    """`spend()` got a proposal that is not the user's, not approved, or already used."""


def propose(
    db: Connection,
    user_id: int,
    app: str,
    item: PaidItem,
    reason: str,
    candidate_id: int | None = None,
    cost: str | None = None,
) -> int | None:
    """Put a paid item in the user's review queue and return the proposal's ID. Spends nothing. `cost` is
    what the item costs when the app's connector reported it.

    None when the app's connector cannot spend this item, or the same proposal exists: one per candidate ever,
    and one pending at a time for an item spent on nobody.
    """
    connector = _connectors().get(app)
    if not connector or item not in connector.capabilities or f"{app}:{item}" in disabled_capabilities():
        return None
    return db.execute(
        text(
            """
            INSERT INTO paid_item_proposals (user_id, app, item, candidate_id, reason, cost)
            SELECT :user_id, :app, :item, :candidate_id, :reason, :cost
            WHERE NOT EXISTS (
                SELECT 1 FROM paid_item_proposals WHERE user_id = :user_id AND app = :app AND item = :item
                AND (candidate_id = :candidate_id OR (CAST(:candidate_id AS bigint) IS NULL AND status = 'pending'))
            )
            ON CONFLICT DO NOTHING RETURNING id
            """
        ),
        {"user_id": user_id, "app": app, "item": item, "candidate_id": candidate_id, "reason": reason, "cost": cost},
    ).scalar_one_or_none()


def waiting(db: Connection, user_id: int) -> list[Row]:
    """The proposals that wait for the user's approval, oldest first."""
    return list(db.execute(text(f"{_SELECT} WHERE p.user_id = :user_id AND {_WAITS} ORDER BY p.id"), {"user_id": user_id}))


def waits_for_approval(db: Connection, user_id: int, candidate_id: int) -> bool:
    """True while a paid item is proposed for this candidate: autopilot leaves the profile to the user."""
    return db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM paid_item_proposals"
            " WHERE candidate_id = :id AND user_id = :user_id AND status = 'pending')"
        ),
        {"id": candidate_id, "user_id": user_id},
    ).scalar_one()


def spend(db: Connection, user_id: int, proposal: Row) -> str:
    """Spend the paid item of a proposal the user approved. The one function that spends a paid item.

    `proposal` is a `paid_item_proposals` row. It is claimed in the database first, so it must be this user's
    and `approved`, and it can be spent once: anything else raises `NotApproved` before the app is touched.
    Returns the new status: `spent`, with an audit entry, or `failed` when the app was not reached or the
    account holds no such item. A failed proposal is never tried again.
    """
    # shortcut: the claim, the spend and the audit entry share the caller's transaction. If the process dies
    # after the app answered, the claim rolls back and the proposal can be approved again. Commit the claim
    # in its own transaction if that ever happens.
    claimed = db.execute(
        text(
            "UPDATE paid_item_proposals SET status = 'spent' WHERE id = :id AND user_id = :user_id"
            " AND status = 'approved' RETURNING id, app, item, candidate_id"
        ),
        {"id": proposal.id, "user_id": user_id},
    ).one_or_none()
    if not claimed:
        raise NotApproved(f"proposal {proposal.id} is not an approved, unused proposal of user {user_id}")
    args, target = [], "account"
    if claimed.candidate_id is not None:
        # The profile must still wait for a swipe. None when the user swiped on it in the meantime.
        args.append(
            db.execute(
                text(
                    "SELECT profile_id FROM swipe_candidates"
                    " WHERE id = :id AND user_id = :user_id AND decision IS NULL FOR UPDATE"
                ),
                {"id": claimed.candidate_id, "user_id": user_id},
            ).scalar_one_or_none()
        )
        target = f"candidate:{claimed.candidate_id}"
    try:
        spent = None not in args and _run(db, user_id, _connectors()[claimed.app](), claimed.item, *args)
    except (CapabilityUnavailable, CapabilityFailed):
        spent = False
    if not spent:
        db.execute(
            text("UPDATE paid_item_proposals SET status = 'failed' WHERE id = :id AND user_id = :user_id"),
            {"id": claimed.id, "user_id": user_id},
        )
        return "failed"
    # A Super Like or Rose is also the swipe on that profile, and the user's own decision.
    db.execute(
        text(
            "UPDATE swipe_candidates SET decision = 'like', decided_at = now()"
            " WHERE id = :id AND user_id = :user_id"
        ),
        {"id": claimed.candidate_id, "user_id": user_id},
    )
    record_action(
        db,
        user_id,
        type=claimed.item,
        app=claimed.app,
        target=target,
        trigger=f"paid item: user approved proposal {claimed.id}",
    )
    return "spent"


def _decide(db: Connection, user_id: int, proposal_id: int, status: str) -> Row:
    """Move a waiting proposal to `status`. 404 if it is not the user's, 409 if it no longer waits."""
    row = db.execute(
        text(
            f"""
            UPDATE paid_item_proposals SET status = :status, decided_at = now()
            WHERE id = (SELECT p.id FROM paid_item_proposals p LEFT JOIN swipe_candidates c ON c.id = p.candidate_id
                        WHERE p.id = :id AND p.user_id = :user_id AND {_WAITS} FOR UPDATE OF p)
            RETURNING id
            """
        ),
        {"id": proposal_id, "user_id": user_id, "status": status},
    ).one_or_none()
    if not row:
        known = db.execute(
            text("SELECT 1 FROM paid_item_proposals WHERE id = :id AND user_id = :user_id"),
            {"id": proposal_id, "user_id": user_id},
        ).one_or_none()
        raise HTTPException(status_code=409 if known else 404, detail="no paid item waits under this id")
    return row


def _read(db: Connection, user_id: int, proposal_id: int) -> Row:
    return db.execute(
        text(f"{_SELECT} WHERE p.id = :id AND p.user_id = :user_id"), {"id": proposal_id, "user_id": user_id}
    ).one()


@router.post("/paid-items/{proposal_id}/approve", response_model=Proposal)
def approve(proposal_id: int, user: CurrentUser, db: Db):
    """Approve a proposed paid item and spend it now. `status` in the answer is `spent` or `failed`."""
    spend(db, user.id, _decide(db, user.id, proposal_id, "approved"))
    return _read(db, user.id, proposal_id)


@router.post("/paid-items/{proposal_id}/decline", response_model=Proposal)
def decline(proposal_id: int, user: CurrentUser, db: Db):
    """Decline a proposed paid item. Nothing is spent."""
    _decide(db, user.id, proposal_id, "declined")
    return _read(db, user.id, proposal_id)
