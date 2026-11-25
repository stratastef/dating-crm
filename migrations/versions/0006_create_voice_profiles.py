"""create voice_profiles table

Revision ID: 0006_voice
Revises: 0005_cards
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.tenancy import user_id_column

revision = "0006_voice"
down_revision = "0005_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # similarity() ranks past chats against a conversation. The extension ships with Postgres.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # One row per user: their questionnaire answers and the style profile written from them.
    op.create_table(
        "voice_profiles",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("answers", JSONB, nullable=False, server_default="{}"),
        # Null until the worker has generated it.
        sa.Column("profile", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id"),
    )


def downgrade() -> None:
    op.drop_table("voice_profiles")
