"""create connector_alerts table

Revision ID: 0007_connector_alerts
Revises: 0006_autopilot
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0007_connector_alerts"
down_revision = "0006_autopilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per failed capability. While a user has a row for an app, that app is copilot-only for them.
    op.create_table(
        "connector_alerts",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("capability", sa.Text, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("connector_alerts")
