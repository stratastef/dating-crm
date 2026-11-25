"""create swipe_candidates table

Revision ID: 0022_swipe_candidates
Revises: 0021_photos
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.tenancy import user_id_column

revision = "0022_swipe_candidates"
down_revision = "0021_photos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per profile a dating app offered the user to swipe on, with the app's suggestion and, once the
    # user swiped, their decision. Decided rows are kept: they are the manual-swipe preference signal.
    op.create_table(
        "swipe_candidates",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("profile_id", sa.Text, nullable=False),  # the dating app's ID of the profile
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("bio", sa.Text, nullable=False),
        sa.Column("photos", JSONB, nullable=False),  # list of URLs
        sa.Column("suggestion", sa.Text, nullable=False),  # like or pass
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),  # which pre-filter suggested: jev or model
        sa.Column("decision", sa.Text),  # like or pass; null until the user swipes
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("user_id", "app", "profile_id"),
    )


def downgrade() -> None:
    op.drop_table("swipe_candidates")
