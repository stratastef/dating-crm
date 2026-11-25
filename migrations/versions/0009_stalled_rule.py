"""add the stalled flag to cards and the silent-days setting to users

Revision ID: 0009_stalled
Revises: 0008_voice
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_stalled"
down_revision = "0008_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stalled is a flag on the card, not a stage. Null means not stalled.
    op.add_column("cards", sa.Column("stalled_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("stalled_after_days", sa.Integer, nullable=False, server_default="3"))
    op.create_check_constraint("users_stalled_after_days_check", "users", "stalled_after_days >= 1")


def downgrade() -> None:
    op.drop_column("users", "stalled_after_days")
    op.drop_column("cards", "stalled_at")
