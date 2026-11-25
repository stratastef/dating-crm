"""add the monthly AI budget cap to users

Revision ID: 0017_ai_budget
Revises: 0016_dashboard
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_ai_budget"
down_revision = "0016_dashboard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The most the user's Claude calls may cost per calendar month, in USD.
    op.add_column("users", sa.Column("ai_budget_usd", sa.Numeric(10, 2), nullable=False, server_default="50"))
    op.create_check_constraint("users_ai_budget_usd_check", "users", "ai_budget_usd >= 0")


def downgrade() -> None:
    op.drop_column("users", "ai_budget_usd")
