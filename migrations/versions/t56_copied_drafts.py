"""a copied draft remembers when it was copied; v1 drafts left approved and never sent are copied

Revision ID: t56_copied_drafts
Revises: t49_invite_codes
"""

import sqlalchemy as sa
from alembic import op

revision = "t56_copied_drafts"
down_revision = "t49_invite_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A newer message from the user than this sends the copied draft (`insert_message()` in `app/cards.py`).
    op.add_column("drafts", sa.Column("copied_at", sa.DateTime(timezone=True)))
    # v1's Approve on a card the app could not send to left the draft `approved`, and no screen showed it again.
    # A draft whose send job still waits is left for the worker to send.
    op.execute(
        """
        UPDATE drafts SET status = 'copied', copied_at = updated_at
        WHERE status = 'approved' AND NOT EXISTS (
            SELECT 1 FROM jobs WHERE jobs.user_id = drafts.user_id AND kind = 'send_draft' AND status = 'queued'
              AND payload->>'draft_id' = CAST(drafts.id AS text))
        """
    )


def downgrade() -> None:
    op.execute("UPDATE drafts SET status = 'approved' WHERE status = 'copied'")
    op.drop_column("drafts", "copied_at")
