"""purge tombstones: a purged person is not stored again, and connector alerts name nobody

Revision ID: 0029_purge_tombstones
Revises: 0028_paid_items
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0029_purge_tombstones"
down_revision = "0028_paid_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # One row per purged match or swipe candidate. `key` is a keyed hash (see `app/tombstones.py`): no name,
    # no app and no ID of the person is stored.
    op.create_table(
        "purge_tombstones",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        user_id_column(),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "key", name="purge_tombstones_user_id_key_key"),
    )
    # Alerts stored `repr()` of the connector's error, whose URL holds match and profile IDs. They outlive
    # a purge, so the old text goes; new alerts store the kind of error only.
    op.execute("UPDATE connector_alerts SET error = reason")


def downgrade() -> None:
    op.drop_table("purge_tombstones")
