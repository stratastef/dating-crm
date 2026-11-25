"""create audit_log table

Revision ID: 0002_audit_log
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

from app.tenancy import user_id_column

revision = "0002_audit_log"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        user_id_column(),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("app", sa.Text, nullable=False),
        sa.Column("target", sa.Text, nullable=False),
        sa.Column("trigger", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "type IN ('message', 'like', 'pass', 'profile_change', 'calendar_hold')", name="audit_log_type_check"
        ),
    )
    # Append-only: reject UPDATE and DELETE. Depth > 1 means the delete cascades from
    # deleting the owning user, which must still work.
    op.execute(
        """
        CREATE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION 'audit_log is append-only';
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_log_append_only()
        """
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.execute("DROP FUNCTION audit_log_append_only()")
