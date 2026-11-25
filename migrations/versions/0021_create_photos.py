"""create the photos table

Revision ID: 0021_photos
Revises: 0020_calendar_holds
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.tenancy import user_id_column

revision = "0021_photos"
down_revision = "0020_calendar_holds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per photo the user uploaded. The file itself is on disk under PHOTOS_DIR.
    op.create_table(
        "photos",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("content_type", sa.Text, nullable=False),
        # 1 is the best photo. Null, like the reason, until the photos are ranked.
        sa.Column("rank", sa.Integer),
        sa.Column("reason", sa.Text),
        # The light edit on offer, and the one the user accepted: {"crop", "exposure", "colour"}.
        sa.Column("suggested_edit", JSONB),
        sa.Column("edit", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("photos")
