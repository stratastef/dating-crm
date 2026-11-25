"""create autonomy_settings and autopilot_pauses tables

Revision ID: 0006_autopilot
Revises: 0005_cards
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0006_autopilot"
down_revision = "0005_cards"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A missing row means the default level, see DEFAULT_LEVELS in app/autopilot.py.
    op.create_table(
        "autonomy_settings",
        user_id_column(),
        sa.Column("job", sa.Text, nullable=False),
        sa.Column("level", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("user_id", "job"),
        sa.CheckConstraint("job IN ('chat', 'profile', 'swipe')", name="autonomy_settings_job_check"),
        sa.CheckConstraint("level IN ('off', 'copilot', 'guardrails', 'full')", name="autonomy_settings_level_check"),
    )
    # A row means paused. `app` is the paused app, or '' for all apps.
    op.create_table(
        "autopilot_pauses",
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "app"),
    )


def downgrade() -> None:
    op.drop_table("autopilot_pauses")
    op.drop_table("autonomy_settings")
