"""create preferences table

Revision ID: 0011_preferences
Revises: 0010_bios
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.tenancy import user_id_column

revision = "0011_preferences"
down_revision = "0010_bios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Append-only: one row per saved version. The highest version per user is the one in force.
    op.create_table(
        "preferences",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("wishes", sa.Text, nullable=False),
        sa.Column("must_haves", JSONB, nullable=False),  # list of strings
        sa.Column("dealbreakers", JSONB, nullable=False),  # list of strings
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "version"),
    )


def downgrade() -> None:
    op.drop_table("preferences")
