"""add the user's time zone, which the app sends on each launch

Revision ID: t54_time_zone
Revises: t61_copilot_only_apps
"""

import sqlalchemy as sa
from alembic import op

revision = "t54_time_zone"
down_revision = "t61_copilot_only_apps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An IANA name such as `Europe/Berlin`. Today's groups follow it.
    op.add_column("users", sa.Column("time_zone", sa.Text, nullable=False, server_default="UTC"))


def downgrade() -> None:
    op.drop_column("users", "time_zone")
