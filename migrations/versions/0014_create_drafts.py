"""create llm_calls and drafts tables

Revision ID: 0014_drafts
Revises: 0013_alert_reason
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0014_drafts"
down_revision = "0013_alert_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per call to Claude, with what it cost. Written only by `app.llm.call()`.
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("purpose", sa.Text, nullable=False),  # which feature called, for example `draft`
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=False),
        sa.Column("output_tokens", sa.Integer, nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llm_calls_user_created", "llm_calls", ["user_id", "created_at"])

    # One row per draft Claude wrote for a card. `original` never changes; `edited` is the user's version.
    op.create_table(
        "drafts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("card_id", sa.BigInteger, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        # No check constraint on status: later tickets add states such as sent and discarded.
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("original", sa.Text, nullable=False),
        sa.Column("edited", sa.Text),  # null until the user edits the draft
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('opener', 'reply')", name="ck_drafts_kind"),
    )
    op.create_index("ix_drafts_user_status", "drafts", ["user_id", "status"])
    op.create_index("ix_drafts_card", "drafts", ["card_id"])


def downgrade() -> None:
    op.drop_table("drafts")
    op.drop_table("llm_calls")
