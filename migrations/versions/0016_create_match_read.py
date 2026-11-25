"""create card_photos and inferences tables, add the protected-trait opt-in

Revision ID: 0016_match_read
Revises: 0015_devices
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0016_match_read"
down_revision = "0015_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guesses about protected traits are made only for a user who opted in. Off unless they say so.
    op.add_column(
        "users", sa.Column("protected_trait_guesses", sa.Boolean, nullable=False, server_default=sa.false())
    )

    # One row per photo on a match's profile. Only a reference is stored, never the image.
    op.create_table(
        "card_photos",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("card_id", sa.BigInteger, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_card_photos_card", "card_photos", ["card_id"])

    # The match read: one row per kind of inference about the match of one card. Every row is about the
    # match; there is no table or column for another person. Deleting the card deletes its inferences.
    op.create_table(
        "inferences",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("card_id", sa.BigInteger, sa.ForeignKey("cards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),  # one of `KINDS` or `PROTECTED` in app/reads.py
        sa.Column("value", sa.Text, nullable=False),  # what Claude inferred
        sa.Column("evidence", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        # The protected trait the inference guesses at, null for none. Such rows exist only by opt-in.
        sa.Column("protected_trait", sa.Text),
        sa.Column("corrected", sa.Text),  # the user's correction; overrides `value` when set
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_inferences_confidence"),
        sa.UniqueConstraint("card_id", "kind", name="uq_inferences_card_kind"),
    )


def downgrade() -> None:
    op.drop_table("inferences")
    op.drop_table("card_photos")
    op.drop_column("users", "protected_trait_guesses")
