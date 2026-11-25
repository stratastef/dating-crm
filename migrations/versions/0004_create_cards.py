"""create cards and messages tables

Revision ID: 0004_cards
Revises: 0003_token_vault
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0004_cards"
down_revision = "0003_token_vault"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cards",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        # The match's ID in the dating app. Null for cards made by hand or from screenshots.
        sa.Column("external_id", sa.Text),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=False),
        sa.Column("stage_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("next_action", sa.Text),
        sa.Column("due_date", sa.Date),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "app", "external_id"),
        sa.CheckConstraint(
            "stage IN ('matched', 'chatting', 'number_swapped', 'date_set', 'dated', 'seeing_them', 'archived')",
            name="cards_stage_check",
        ),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("card_id", sa.BigInteger, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False, index=True),
        # The message's ID in the dating app. Null for messages typed in or read from screenshots.
        sa.Column("external_id", sa.Text),
        sa.Column("sender", sa.Text, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("card_id", "external_id"),
        sa.CheckConstraint("sender IN ('me', 'them')", name="messages_sender_check"),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("cards")
