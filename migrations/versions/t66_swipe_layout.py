"""the Swipe layout each user picks, and the age and distance of a swipe candidate

Revision ID: t66_swipe_layout
Revises: t55_review_context
"""

import sqlalchemy as sa
from alembic import op

revision = "t66_swipe_layout"
down_revision = "t55_review_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null until the user picks one; the app shows one at a time meanwhile (ADR 0004).
    op.add_column("users", sa.Column("swipe_layout", sa.Text))
    op.create_check_constraint("users_swipe_layout", "users", "swipe_layout IN ('one_at_a_time', 'list')")
    # Null when the dating app does not say.
    op.add_column("swipe_candidates", sa.Column("age", sa.Integer))
    op.add_column("swipe_candidates", sa.Column("distance_mi", sa.Integer))


def downgrade() -> None:
    op.drop_column("swipe_candidates", "distance_mi")
    op.drop_column("swipe_candidates", "age")
    op.drop_column("users", "swipe_layout")
