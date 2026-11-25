"""create devices table

Revision ID: 0011_devices
Revises: 0010_bios
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0011_devices"
down_revision = "0010_bios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per iPhone that receives the user's push notifications.
    op.create_table(
        "devices",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        # The APNs device token, in hex. A phone has one, whoever is signed in on it.
        sa.Column("token", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("devices")
