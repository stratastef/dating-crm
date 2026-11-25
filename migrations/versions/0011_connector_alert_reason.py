"""add reason to connector_alerts

Revision ID: 0011_alert_reason
Revises: 0010_bios
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_alert_reason"
down_revision = "0010_bios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Why the connector failed: 'auth failure', 'ban signal' or 'transient'. Rows from before this are unclassified.
    op.add_column("connector_alerts", sa.Column("reason", sa.Text, nullable=False, server_default="transient"))


def downgrade() -> None:
    op.drop_column("connector_alerts", "reason")
