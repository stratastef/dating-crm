"""invite codes: one-time codes that let one person create an account

Revision ID: t49_invite_codes
Revises: t55_review_context
"""

import sqlalchemy as sa
from alembic import op

revision = "t49_invite_codes"
down_revision = "t55_review_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Not a tenant table: an invite code belongs to nobody until it creates an account.
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("code_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        # Set when the invite code creates an account; it creates no other.
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    # The invite code a code request for a number with no account came with; sign-in uses it up.
    op.add_column("sign_in_codes", sa.Column("invite_code_id", sa.BigInteger, sa.ForeignKey("invite_codes.id")))


def downgrade() -> None:
    op.drop_column("sign_in_codes", "invite_code_id")
    op.drop_table("invite_codes")
