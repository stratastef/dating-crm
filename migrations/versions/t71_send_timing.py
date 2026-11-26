"""send timing: each draft's send time and timing reason, and the user's night window

Revision ID: t71_send_timing
Revises: t67_stages_reached
"""

import sqlalchemy as sa
from alembic import op

revision = "t71_send_timing"
down_revision = "t67_stages_reached"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null on drafts written before send timing.
    op.add_column("drafts", sa.Column("send_at", sa.DateTime(timezone=True)))
    op.add_column("drafts", sa.Column("timing_reason", sa.Text, nullable=False, server_default=""))
    # Whole hours of the user's day, in their time zone. A start after the end wraps past midnight.
    op.add_column("users", sa.Column("night_window_start", sa.SmallInteger, nullable=False, server_default="1"))
    op.add_column("users", sa.Column("night_window_end", sa.SmallInteger, nullable=False, server_default="7"))
    op.create_check_constraint(
        "night_window_hours", "users", "night_window_start BETWEEN 0 AND 23 AND night_window_end BETWEEN 0 AND 23"
    )


def downgrade() -> None:
    op.drop_constraint("night_window_hours", "users")
    op.drop_column("users", "night_window_end")
    op.drop_column("users", "night_window_start")
    op.drop_column("drafts", "timing_reason")
    op.drop_column("drafts", "send_at")
