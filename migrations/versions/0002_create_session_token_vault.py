"""create session token vault tables

Revision ID: 0002_token_vault
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0002_token_vault"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vault_keys",
        user_id_column(),
        # The user's data key, encrypted with the master key from the environment.
        sa.Column("wrapped_key", sa.Text, nullable=False),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "session_tokens",
        user_id_column(),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("ciphertext", sa.Text, nullable=False),
        sa.UniqueConstraint("user_id", "app"),
    )


def downgrade() -> None:
    op.drop_table("session_tokens")
    op.drop_table("vault_keys")
