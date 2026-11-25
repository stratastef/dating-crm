"""Worker process entry point: `python -m app.worker`.

It has no jobs yet. Connectors and autopilot jobs, queued in Postgres, attach here.
"""

import logging
import time

from sqlalchemy import create_engine, text

from app.db import database_url

log = logging.getLogger("worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_engine(database_url(), pool_pre_ping=True)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    log.info("worker started, database reachable")
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
