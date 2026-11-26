"""dashboard funnel: record when each card first reached Chatting, Date set and Dated

Revision ID: t67_stages_reached
Revises: t53_chat_topic
"""

import sqlalchemy as sa
from alembic import op

revision = "t67_stages_reached"
down_revision = "t53_chat_topic"
branch_labels = None
depends_on = None

# Each column is set the first time a card reaches its stage or a later one, and never moves or clears after.
# Matched is `created_at`. Number swapped and Seeing them are not funnel stages; Archived reaches none.
_REACHED = {
    "chatting_at": "('chatting', 'number_swapped', 'date_set', 'dated', 'seeing_them')",
    "date_set_at": "('date_set', 'dated', 'seeing_them')",
    "dated_at": "('dated', 'seeing_them')",
}


def upgrade() -> None:
    for column in _REACHED:
        op.add_column("cards", sa.Column(column, sa.DateTime(timezone=True)))
    # shortcut: a card from before this migration counts every stage it passed at its last stage change,
    # and an archived one counts none. Exact from here on, so no upgrade needed.
    op.execute(
        "UPDATE cards SET "
        + ", ".join(
            f"{column} = CASE WHEN stage IN {stages} THEN stage_changed_at END" for column, stages in _REACHED.items()
        )
    )
    # A trigger, so every writer of `stage` is covered (as `cards_label_led_to_date`).
    op.execute(
        "CREATE FUNCTION cards_stage_reached() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        + " ".join(
            f"IF NEW.stage IN {stages} THEN NEW.{column} := coalesce(NEW.{column}, now()); END IF;"
            for column, stages in _REACHED.items()
        )
        + " RETURN NEW; END $$"
    )
    op.execute(
        "CREATE TRIGGER cards_stage_reached BEFORE INSERT OR UPDATE OF stage ON cards"
        " FOR EACH ROW EXECUTE FUNCTION cards_stage_reached()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER cards_stage_reached ON cards")
    op.execute("DROP FUNCTION cards_stage_reached()")
    for column in _REACHED:
        op.drop_column("cards", column)
