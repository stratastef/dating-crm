"""a paid item keeps the cost the dating app reported for it

Revision ID: t55_review_context
Revises: t54_time_zone
"""

import sqlalchemy as sa
from alembic import op

revision = "t55_review_context"
down_revision = "t54_time_zone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # In the app's words ("$1.99"); null when the connector reported none.
    op.add_column("paid_item_proposals", sa.Column("cost", sa.Text))


def downgrade() -> None:
    op.drop_column("paid_item_proposals", "cost")
