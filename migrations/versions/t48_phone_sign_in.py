"""sign in by phone number and sign-in code: a phone number per user, one API token per signed-in device

Revision ID: t48_phone_sign_in
Revises: t46_autonomy_levels
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "t48_phone_sign_in"
down_revision = "t46_autonomy_levels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The phone number (E.164) is the account's identity; email is kept for v1 accounts.
    op.add_column("users", sa.Column("phone", sa.Text, unique=True))
    op.alter_column("users", "email", nullable=True)

    # One row per signed-in device. The v1 token moves here, so it keeps working.
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("token_hash", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("INSERT INTO api_tokens (user_id, token_hash, created_at) SELECT id, token_hash, created_at FROM users")
    op.drop_column("users", "token_hash")

    # A push device belongs to the token that registered it, so signing out stops its pushes.
    op.add_column(
        "devices",
        sa.Column("api_token_id", sa.BigInteger, sa.ForeignKey("api_tokens.id", ondelete="CASCADE"), index=True),
    )
    op.execute("UPDATE devices d SET api_token_id = (SELECT id FROM api_tokens t WHERE t.user_id = d.user_id)")
    op.alter_column("devices", "api_token_id", nullable=False)

    # One row per sign-in code request, also the refused ones, which the rate limits count.
    op.create_table(
        "sign_in_codes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        # The account the code signs in to; null when the phone number has none.
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("phone", sa.Text, nullable=False),
        sa.Column("ip", sa.Text, nullable=False),
        # Null when no code was sent, or once it was used or replaced by a newer one.
        sa.Column("code_hash", sa.Text),
        sa.Column("tries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("sign_in_codes_phone_created_at", "sign_in_codes", ["phone", "created_at"])
    op.create_index("sign_in_codes_ip_created_at", "sign_in_codes", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_table("sign_in_codes")
    op.drop_column("devices", "api_token_id")
    # v1 had one token per user: keep the oldest. A user without one gets a hash no token matches.
    op.add_column("users", sa.Column("token_hash", sa.Text, unique=True))
    op.execute(
        "UPDATE users u SET token_hash = COALESCE("
        " (SELECT token_hash FROM api_tokens t WHERE t.user_id = u.id ORDER BY id LIMIT 1), 'none-' || u.id)"
    )
    op.alter_column("users", "token_hash", nullable=False)
    op.drop_table("api_tokens")
    op.execute("UPDATE users SET email = 'phone-' || id || '@invalid' WHERE email IS NULL")
    op.alter_column("users", "email", nullable=False)
    op.drop_column("users", "phone")
