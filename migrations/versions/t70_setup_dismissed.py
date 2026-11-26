"""the user's choice to hide "Finish setup" on Today

Revision ID: t70_setup_dismissed
Revises: t53_chat_topic
"""

import sqlalchemy as sa
from alembic import op

revision = "t70_setup_dismissed"
down_revision = "t53_chat_topic"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("setup_dismissed", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "setup_dismissed")
