"""rename the autonomy levels guardrails and full to autopilot and full_autopilot

Revision ID: t46_autonomy_levels
Revises: 0031_ai_disclosed
"""

from alembic import op

revision = "t46_autonomy_levels"
down_revision = "0031_ai_disclosed"
branch_labels = None
depends_on = None


def _rename(levels: dict[str, str]) -> None:
    op.drop_constraint("autonomy_settings_level_check", "autonomy_settings")
    for old, new in levels.items():
        op.execute(f"UPDATE autonomy_settings SET level = '{new}' WHERE level = '{old}'")
    allowed = ", ".join(f"'{level}'" for level in ["off", "copilot", *levels.values()])
    op.create_check_constraint("autonomy_settings_level_check", "autonomy_settings", f"level IN ({allowed})")


def upgrade() -> None:
    _rename({"guardrails": "autopilot", "full": "full_autopilot"})


def downgrade() -> None:
    _rename({"autopilot": "guardrails", "full_autopilot": "full"})
