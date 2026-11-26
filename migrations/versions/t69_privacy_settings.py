"""push name previews and Blur photos, both off by default

Revision ID: t69_privacy_settings
Revises: t70_setup_dismissed
"""

import sqlalchemy as sa
from alembic import op

revision = "t69_privacy_settings"
down_revision = "t70_setup_dismissed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("push_name_previews", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("blur_photos", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "blur_photos")
    op.drop_column("users", "push_name_previews")
