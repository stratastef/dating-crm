"""store Jev check results on messages and drafts

Revision ID: 0016_jev_checks
Revises: 0015_devices
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_jev_checks"
down_revision = "0015_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The handover checks an incoming message hit. Null: not checked (the user's own messages, older rows).
    op.add_column("messages", sa.Column("handover", sa.ARRAY(sa.Text)))
    # The guardrail checks the draft's current text hit. Null: not checked (older rows).
    op.add_column("drafts", sa.Column("guardrail", sa.ARRAY(sa.Text)))
    op.add_column("drafts", sa.Column("hot_lead", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("drafts", "hot_lead")
    op.drop_column("drafts", "guardrail")
    op.drop_column("messages", "handover")
