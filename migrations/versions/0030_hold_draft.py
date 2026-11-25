"""calendar holds know the draft that offered them

Revision ID: 0030_hold_draft
Revises: 0029_purge_tombstones
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_hold_draft"
down_revision = "0029_purge_tombstones"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The draft whose text offers the slot, so that dismissing or failing that draft releases the hold.
    # Null for a hold made before this column, or by code that offers a slot without a draft.
    op.add_column(
        "calendar_holds", sa.Column("draft_id", sa.BigInteger, sa.ForeignKey("drafts.id", ondelete="SET NULL"))
    )


def downgrade() -> None:
    op.drop_column("calendar_holds", "draft_id")
