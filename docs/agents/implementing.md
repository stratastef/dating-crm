# Implementing a ticket as a subagent

For an implementer started by `/implement-spec` or `/implement`, and for whoever orchestrates them.

## Implementer

- **Base.** Your worktree starts from `main`. Reset it onto the integration branch tip before your first edit.
- **Seams are yours.** No user is present. Where `/tdd` says to confirm a seam with the user, choose the smallest reasonable one and name it in your report.
- **Read narrowly.** `README.md` for run, test and tenancy; then only the `docs/modules/` files your ticket touches.
- **Migrations.** Name the revision `t<ticket>_<slug>`. Leave `down_revision` on the head you started from; the merge re-points it.
- **No registration.** A module joins the API by defining `router` and the worker by using `@handler`. `app/main.py` and `app/worker.py` stay untouched.
- **Done means run.** `uv run pytest`, `uv run ruff check .`, `uv run pyright`, and `scripts/ios-test` if you touched `ios/`. A screen you added is opened once in the simulator.
- **Your own machine state.** Other implementers run beside you. Scratch files go in `$TMPDIR/dcrm-t<ticket>/`. A simulator for screenshots is one you create, address by UDID and delete when done. Docker and Postgres on `localhost:5432` are shared: if one stops answering, wait and retry, and report it if it stays down.
- **Docs.** Write your module's doc in `docs/modules/<module>.md` and add one line to the list in `README.md`. A screen's doc is the "On the phone" section of its feature's module doc; `docs/modules/ios-app-shell.md` holds only what every screen shares.
- **Report.** End it with "Owner decisions needed:" and each rule you chose where the spec or ticket is silent or contradicts itself, or "none".

## Orchestrator

- **Four implementers at most** at one time. Seven exhausted the usage limit mid-ticket.
- **One ticket per module at a time.** Two tickets whose "What to build" names the same module run one after the other: parallel edits to one composer cost a second merge.
- **Before each wave**, check `df -h ~`. Under 20 GB free, launch fewer implementers or clean up first: a full disk took Docker and Postgres down mid-build.
- **Before iOS tickets**, allow the iOS simulator tool for the session, so implementers can tap what they build.
- **Merge with** `scripts/merge-ticket <branch>`: it re-points the migration, runs the tests and removes the worktree.
- **After each iOS merge**, run `scripts/ios-test` on the integration branch.
- **After each push**, `gh pr checks` is green before the next merge and before the PR is marked ready. CI runs on pull requests and `main` only; the iOS job runs on the owner's Mac when `ios/` changed, and waits while that Mac sleeps.
- **Owner decisions** from a report go to the owner when that ticket merges.
- **Before review**, run `docker compose up --build --wait` once. Unit tests never start the built image.
