"""swipe autopilot: swipe limits per user, which swipes were unattended, and purging a candidate

Revision ID: 0025_swipe_autopilot
Revises: 0024_swipe_candidates
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_swipe_autopilot"
down_revision = "0024_swipe_candidates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # How many profiles swipe autopilot may swipe on, per app: in one run of the job and in any 24 hours.
    # The defaults are low on purpose: fast swiping is a ban signal.
    op.add_column("users", sa.Column("swipes_per_run", sa.Integer, nullable=False, server_default="5"))
    op.add_column("users", sa.Column("swipes_per_day", sa.Integer, nullable=False, server_default="20"))
    # True when swipe autopilot decided, false when the user did: only the user's swipes are a preference signal.
    op.add_column(
        "swipe_candidates", sa.Column("unattended", sa.Boolean, nullable=False, server_default=sa.false())
    )
    # Deleting a candidate deletes the audit entries about that person: target `candidate:<swipe_candidates.id>`,
    # alone or followed by a space and more text. Same way as `cards_purge_audit_log` (see 0023_purge).
    op.execute(
        """
        CREATE FUNCTION swipe_candidates_purge_audit_log() RETURNS trigger AS $$
        BEGIN
            DELETE FROM audit_log
            WHERE user_id = OLD.user_id AND starts_with(target || ' ', 'candidate:' || OLD.id || ' ');
            RETURN OLD;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER swipe_candidates_purge_audit_log BEFORE DELETE ON swipe_candidates
        FOR EACH ROW EXECUTE FUNCTION swipe_candidates_purge_audit_log()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER swipe_candidates_purge_audit_log ON swipe_candidates")
    op.execute("DROP FUNCTION swipe_candidates_purge_audit_log()")
    op.drop_column("swipe_candidates", "unattended")
    op.drop_column("users", "swipes_per_day")
    op.drop_column("users", "swipes_per_run")
