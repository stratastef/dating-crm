"""purge: a deleted card takes its audit entries with it, and the purge is an audit type

Revision ID: 0020_purge
Revises: 0019_match_read
"""

from alembic import op

revision = "0020_purge"
down_revision = "0019_match_read"
branch_labels = None
depends_on = None

_TYPES = "'message', 'like', 'pass', 'profile_change', 'calendar_hold'"


def _type_check(types: str) -> None:
    op.drop_constraint("audit_log_type_check", "audit_log")
    op.create_check_constraint("audit_log_type_check", "audit_log", f"type IN ({types})")


def upgrade() -> None:
    _type_check(f"{_TYPES}, 'purge'")
    # Deleting a card deletes the audit entries about that match: target `card:<cards.id>`, or
    # `match:<cards.external_id>` on the same app. The append-only trigger on audit_log lets a delete
    # through only from inside another trigger, so this is the one way such entries are removed.
    op.execute(
        """
        CREATE FUNCTION cards_purge_audit_log() RETURNS trigger AS $$
        BEGIN
            DELETE FROM audit_log
            WHERE user_id = OLD.user_id
              AND (target = 'card:' || OLD.id OR (app = OLD.app AND target = 'match:' || OLD.external_id));
            RETURN OLD;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER cards_purge_audit_log BEFORE DELETE ON cards
        FOR EACH ROW EXECUTE FUNCTION cards_purge_audit_log()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER cards_purge_audit_log ON cards")
    op.execute("DROP FUNCTION cards_purge_audit_log()")
    # shortcut: fails while `purge` entries exist; the log is append-only, so they cannot be removed here.
    _type_check(_TYPES)
