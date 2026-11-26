"""a message records whether autopilot sent it alone, so the chat can mark it

Revision ID: t59_sent_by_autopilot
Revises: t67_stages_reached
"""

import sqlalchemy as sa
from alembic import op

revision = "t59_sent_by_autopilot"
down_revision = "t67_stages_reached"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Messages stored before this are unmarked: nothing recorded which sends autopilot made alone.
    op.add_column(
        "messages", sa.Column("sent_by_autopilot", sa.Boolean(), nullable=False, server_default=sa.false())
    )


def downgrade() -> None:
    op.drop_column("messages", "sent_by_autopilot")
