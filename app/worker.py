"""Worker process entry point: `python -m app.worker`.

It runs the jobs queued in Postgres (see `app/jobs.py`), one at a time. Start more workers to run jobs in parallel.
"""

import logging
import time

from sqlalchemy import create_engine, text

from app.db import database_url
from app.jobs import enqueue_recurring, run_once
from app.modules import modules

list(modules())  # importing a module registers its job handlers

log = logging.getLogger("worker")

POLL_SECONDS = 1


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    log.info("worker started, database reachable")
    while True:
        try:
            enqueue_recurring(engine)
            idle = not run_once(engine)
        except Exception:  # database unreachable: keep the worker alive and try again
            log.exception("could not poll for jobs")
            idle = True
        if idle:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
