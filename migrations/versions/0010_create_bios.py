"""create bios table

Revision ID: 0010_bios
Revises: 0009_stalled
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.tenancy import user_id_column

revision = "0010_bios"
down_revision = "0009_stalled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per user and dating app: the bio and prompt answers the user accepted.
    op.create_table(
        "bios",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("bio", sa.Text, nullable=False),
        sa.Column("prompts", JSONB, nullable=False),  # prompt -> answer
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "app"),
    )


def downgrade() -> None:
    op.drop_table("bios")
