"""a card keeps the topic of its chat, written with its latest draft

Revision ID: t53_chat_topic
Revises: t49_invite_codes
"""

import sqlalchemy as sa
from alembic import op

revision = "t53_chat_topic"
down_revision = "t49_invite_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A few words, such as "museums". Empty until the card's first draft.
    op.add_column("cards", sa.Column("topic", sa.Text, nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("cards", "topic")
