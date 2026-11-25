# Implementing a ticket as a subagent

For an implementer started by `/implement-spec` or `/implement`, and for whoever orchestrates them.

## Implementer

- **Base.** Your worktree starts from `main`. Reset it onto the integration branch tip before your first edit.
- **Seams are yours.** No user is present. Where `/tdd` says to confirm a seam with the user, choose the smallest reasonable one and name it in your report.
- **Read narrowly.** `README.md` for run, test and tenancy; then only the `docs/modules/` files your ticket touches.
- **Migrations.** Name the revision `t<ticket>_<slug>`. Leave `down_revision` on the head you started from; the merge re-points it.
- **No registration.** A module joins the API by defining `router` and the worker by using `@handler`. `app/main.py` and `app/worker.py` stay untouched.
- **Done means run.** `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and `xcodebuild test` if you touched `ios/`. A screen you added is opened once in the simulator.
- **Docs.** Write your module's doc in `docs/modules/<module>.md` and add one line to the list in `README.md`.

## Orchestrator

- **Four implementers at most** at one time. Seven exhausted the usage limit mid-ticket.
- **Merge with** `scripts/merge-ticket <branch>`: it re-points the migration, runs the tests and removes the worktree.
- **After each iOS merge**, run `xcodebuild test` on the integration branch.
- **Before review**, run `docker compose up --build --wait` once. Unit tests never start the built image.
