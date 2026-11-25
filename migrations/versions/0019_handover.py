"""pause a card for handover

Revision ID: 0019_handover
Revises: 0018_jev_checks
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_handover"
down_revision = "0018_jev_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null: autopilot may chat. `pending`: a handover trigger hit and the user has not answered yet.
    # `taken_over`: the user keeps the chat manual until they hand it back.
    op.add_column("cards", sa.Column("handover", sa.Text))
    op.create_check_constraint("cards_handover_check", "cards", "handover IN ('pending', 'taken_over')")
    # The replies suggested for the pending handover.
    op.add_column("cards", sa.Column("handover_suggestions", sa.ARRAY(sa.Text), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("cards", "handover_suggestions")
    op.drop_constraint("cards_handover_check", "cards")
    op.drop_column("cards", "handover")
