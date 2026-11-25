"""paid items: proposals that wait for the user's approval, and their audit types

Revision ID: 0028_paid_items
Revises: 0027_feedback
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0028_paid_items"
down_revision = "0027_feedback"
branch_labels = None
depends_on = None

_PAID = ("super_like", "rose", "boost")


def _audit_types(add: bool) -> None:
    """Add the paid items to, or remove them from, the audit types, whatever the other types are by now."""
    bind = op.get_bind()
    definition = bind.execute(
        sa.text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'audit_log_type_check'")
    ).scalar_one()
    # The definition reads `CHECK ((type = ANY (ARRAY['message'::text, ...])))`.
    types = [part.split("'")[1] for part in definition.split("ARRAY[")[1].split("]")[0].split(",")]
    types = [type for type in types if type not in _PAID] + (list(_PAID) if add else [])
    op.drop_constraint("audit_log_type_check", "audit_log")
    op.create_check_constraint(
        "audit_log_type_check", "audit_log", f"type IN ({', '.join(repr(type) for type in types)})"
    )


def upgrade() -> None:
    # One row per paid item the app proposes to spend. Nothing is spent while `status` is `pending`.
    op.create_table(
        "paid_item_proposals",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("item", sa.Text, nullable=False),
        # The profile the item is spent on; null for an item spent on nobody (a Boost). At most one proposal
        # per candidate, and purging the candidate deletes it.
        sa.Column(
            "candidate_id", sa.BigInteger, sa.ForeignKey("swipe_candidates.id", ondelete="CASCADE"), unique=True
        ),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("item IN ('super_like', 'rose', 'boost')", name="paid_item_proposals_item_check"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'declined', 'spent', 'failed')",
            name="paid_item_proposals_status_check",
        ),
    )
    _audit_types(add=True)


def downgrade() -> None:
    _audit_types(add=False)
    op.drop_table("paid_item_proposals")
