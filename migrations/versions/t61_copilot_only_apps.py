"""the dating apps a user chose to keep copilot-only

Revision ID: t61_copilot_only_apps
Revises: t48_phone_sign_in
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "t61_copilot_only_apps"
down_revision = "t48_phone_sign_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per app the user marked copilot-only. A fresh session token for the app deletes it.
    op.create_table(
        "copilot_only_apps",
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "app"),
    )


def downgrade() -> None:
    op.drop_table("copilot_only_apps")
