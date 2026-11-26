"""the dating apps whose first sync since a connect or reconnect has not run yet

Revision ID: review_first_syncs
Revises: t71_send_timing
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "review_first_syncs"
down_revision = "t71_send_timing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A session token stored for an app adds a row; the first sync of the app after it deletes the row. The matches
    # that sync finds were there before the connect: chat autopilot writes them no opener.
    op.create_table(
        "first_syncs",
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "app"),
    )


def downgrade() -> None:
    op.drop_table("first_syncs")
