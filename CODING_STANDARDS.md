# Coding standards

Read during review. These are the judgement calls no tool checks. Mechanical rules are checks, listed last.

## Rules that protect a person

A rule from the spec that protects a match or the user (handover, guardrail, protected traits, paid items, purge, budget, tenancy) is **structural**:

- **Enforced in code.** The code path refuses the action. A sentence in a prompt asking the model to behave is extra, never the enforcement.
- **One test per rule**, named after the rule, that goes red when the enforcement is removed.
- **Checked independently.** A model's label on its own output (`protected_trait: false`) is a claim. A second check that never saw that label decides.
- **Fail closed.** When a classifier, a connector or a budget lookup cannot answer, the action stops and the user is asked. Unattended sending, swiping and spending all stop.
- **One gate per action.** Each unattended action has a single function every caller goes through (`queue_send`, `apply_decision`, `paid_items.spend`). A second path to the same action is a defect.

## Consistency across modules

- A new module follows the nearest existing one: same route style, same helper (`card_lookup`, `llm.call`, `jev.*`, `record_action`), same test fixtures.
- An external service is reached through one seam that tests stub. A direct SDK import outside its seam is a defect.
- A doc in `docs/modules/` changes in the same commit as the behaviour it describes.
- A shortcut with a known limit carries a `shortcut:` comment that names the limit and when to upgrade.

## Checked by tools, so skip in review

- Lint and types: `uv run ruff check .`, `uv run pyright`.
- Every SQL statement names `user_id`: `tests/test_tenancy_sql.py`.
- Every tenant table has `user_id`; Alembic has one head: `tests/test_auth.py`, `tests/test_migrations.py`.
- Paid capabilities reached only through `paid_items.spend()`: `tests/test_paid_items.py`.
- The built stack starts and iOS tests pass: CI jobs `stack` and `ios`.
