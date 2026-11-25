import os
import subprocess
import sys
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from app.auth import create_user
from app.db import database_url
from app.main import create_app


@pytest.fixture(scope="session", autouse=True)
def database():
    """Each test run gets its own migrated database on the Postgres server in DATABASE_URL.

    Runs from sibling worktrees share one server without sharing data.
    """
    server = make_url(database_url())
    name = f"test_{uuid.uuid4().hex}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    os.environ["DATABASE_URL"] = server.set(database=name).render_as_string(hide_password=False)
    try:
        subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
        yield
    finally:
        os.environ["DATABASE_URL"] = server.render_as_string(hide_password=False)
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(autouse=True)
def master_key(monkeypatch):
    monkeypatch.setenv("TOKEN_VAULT_MASTER_KEY", Fernet.generate_key().decode())


@pytest.fixture
def app(database):
    app = create_app()
    yield app
    # Every tenant table references users with ON DELETE CASCADE, so this empties them all.
    with app.state.engine.begin() as connection:
        connection.execute(text("TRUNCATE users CASCADE"))
    app.state.engine.dispose()


@pytest.fixture
def client_for(app):
    """`client_for("a@example.com")` creates that user and returns a client authenticated as them."""

    def client_for(email: str) -> TestClient:
        with app.state.engine.begin() as connection:
            token = create_user(connection, email)
        return TestClient(app, headers={"Authorization": f"Bearer {token}"})

    return client_for


@pytest.fixture
def client(client_for):
    """A client authenticated as a fresh user, on a clean database."""
    return client_for("user@example.com")
