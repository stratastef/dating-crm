"""create calendar holds table

Revision ID: 0017_calendar_holds
Revises: 0016_dashboard
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.tenancy import user_id_column

revision = "0017_calendar_holds"
down_revision = "0016_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Lets one exclusion constraint compare `user_id` (equality) next to `slot` (overlap).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    # One row per time slot offered to a match. A released hold is deleted; the audit log keeps its history.
    op.create_table(
        "calendar_holds",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("card_id", sa.BigInteger, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("slot", postgresql.TSTZRANGE, nullable=False),
        # The Google Calendar event. Null only between the insert and Google's answer, inside one transaction.
        sa.Column("event_id", sa.Text),
        # `held` is a tentative event, `confirmed` the event of a date that is set.
        sa.Column("status", sa.Text, nullable=False, server_default="held"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('held', 'confirmed')", name="calendar_holds_status_check"),
        sa.CheckConstraint("NOT isempty(slot)", name="calendar_holds_slot_not_empty"),
    )
    # The rule that two matches never get the same slot: no two rows of one user may overlap.
    op.execute(
        "ALTER TABLE calendar_holds ADD CONSTRAINT calendar_holds_no_overlap"
        " EXCLUDE USING gist (user_id WITH =, slot WITH &&)"
    )


def downgrade() -> None:
    op.drop_table("calendar_holds")
