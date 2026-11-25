"""add the date rating and note to cards

Revision ID: 0011_date_rating
Revises: 0010_bios
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_date_rating"
down_revision = "0010_bios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Both are null until the user rates the date.
    op.add_column("cards", sa.Column("date_rating", sa.SmallInteger))
    op.add_column("cards", sa.Column("date_note", sa.Text))
    op.create_check_constraint("cards_date_rating_check", "cards", "date_rating BETWEEN 1 AND 5")


def downgrade() -> None:
    op.drop_column("cards", "date_note")
    op.drop_column("cards", "date_rating")
