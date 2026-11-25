import os

# Default matches the `db` service in compose.yaml, published on localhost.
DEFAULT_DATABASE_URL = "postgresql+psycopg://app:app@localhost:5432/app"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
