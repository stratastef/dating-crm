"""record app time and when a date was rated

Revision ID: 0016_dashboard
Revises: 0015_devices
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0016_dashboard"
down_revision = "0015_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per stretch of foreground time the app reports.
    op.create_table(
        "app_time",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("seconds", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # The moment of the first rating: it puts the date in a week on the dashboard.
    op.add_column("cards", sa.Column("date_rated_at", sa.DateTime(timezone=True)))
    # Dates rated before this column existed count in the week of their last stage change.
    op.execute("UPDATE cards SET date_rated_at = stage_changed_at WHERE date_rating IS NOT NULL")


def downgrade() -> None:
    op.drop_column("cards", "date_rated_at")
    op.drop_table("app_time")
