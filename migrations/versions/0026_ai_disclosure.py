"""AI disclosure setting

Revision ID: 0026_ai_disclosure
Revises: 0025_swipe_autopilot
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_ai_disclosure"
down_revision = "0025_swipe_autopilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # On: the first message chat autopilot sends to a match alone says that an AI helps write the messages.
    op.add_column("users", sa.Column("ai_disclosure", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("users", "ai_disclosure")
