"""the card says whether the AI disclosure was sent to its match

Revision ID: 0031_ai_disclosed
Revises: 0030_hold_draft
"""

import sqlalchemy as sa
from alembic import op

revision = "0031_ai_disclosed"
down_revision = "0030_hold_draft"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cards", sa.Column("ai_disclosed", sa.Boolean, nullable=False, server_default=sa.false()))
    # Until now "disclosed" was read from the audit log: a message sent to the card by chat autopilot.
    op.execute(
        """
        UPDATE cards SET ai_disclosed = true
        WHERE EXISTS (SELECT 1 FROM audit_log a WHERE a.user_id = cards.user_id AND a.type = 'message'
                      AND a.target = 'card:' || cards.id AND a.trigger LIKE 'chat autopilot%')
        """
    )


def downgrade() -> None:
    op.drop_column("cards", "ai_disclosed")
