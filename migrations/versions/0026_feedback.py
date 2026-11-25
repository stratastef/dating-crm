"""feedback loop: label each card with whether its chat led to a date

Revision ID: 0026_feedback
Revises: 0025_swipe_autopilot
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_feedback"
down_revision = "0025_swipe_autopilot"
branch_labels = None
depends_on = None

_LED_TO_DATE = "stage IN ('date_set', 'dated', 'seeing_them') OR date_rating IS NOT NULL"


def upgrade() -> None:
    op.add_column("cards", sa.Column("led_to_date", sa.Boolean, nullable=False, server_default=sa.false()))
    op.execute(f"UPDATE cards SET led_to_date = true WHERE {_LED_TO_DATE}")
    # A trigger, so every writer of `stage` is covered. The label is never unset: an archived card keeps it.
    op.execute(
        """
        CREATE FUNCTION cards_label_led_to_date() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.led_to_date := NEW.led_to_date
                OR NEW.stage IN ('date_set', 'dated', 'seeing_them') OR NEW.date_rating IS NOT NULL;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER cards_label_led_to_date BEFORE INSERT OR UPDATE ON cards
        FOR EACH ROW EXECUTE FUNCTION cards_label_led_to_date()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER cards_label_led_to_date ON cards")
    op.execute("DROP FUNCTION cards_label_led_to_date()")
    op.drop_column("cards", "led_to_date")
