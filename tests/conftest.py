import os
import subprocess
import sys
import uuid

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from app.auth import create_user
from app.db import database_url
from app.llm import Completion
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


class StubLlm:
    """Stands in for `app.llm.complete`. Set `reply` to choose the text; `prompts` records what was sent."""

    def __init__(self):
        self.reply = "stub reply"
        self.prompts: list[str] = []
        self.images: list[list[tuple[str, bytes]]] = []  # per call: the (content type, bytes) pairs sent

    def __call__(self, system: str, prompt: str, max_tokens: int = 16000, images=()) -> Completion:
        self.prompts.append(prompt)
        self.images.append(list(images))
        return Completion(text=self.reply, model="stub", input_tokens=1, output_tokens=1)


@pytest.fixture(autouse=True)
def llm(monkeypatch):
    """Every test gets the stub, so no test can call the real Claude API."""
    stub = StubLlm()
    monkeypatch.setattr("app.llm.complete", stub)
    return stub


class StubApns:
    """Stands in for `app.push.post`, the one function that calls Apple. `sent` records each push.

    A device token listed in `answers` gets that `(status, reason)`; the rest get `(200, "")`.
    """

    def __init__(self):
        self.sent: list[dict] = []
        self.answers: dict[str, tuple[int, str]] = {}

    def __call__(self, url: str, headers: dict, payload: dict) -> tuple[int, str]:
        self.sent.append({"url": url, "headers": headers, "payload": payload})
        return self.answers.get(url.rsplit("/", 1)[-1], (200, ""))


APNS_KEY = ec.generate_private_key(ec.SECP256R1())


@pytest.fixture(autouse=True)
def apns(monkeypatch):
    """Every test gets the stub and a throwaway APNs key, so no test can call Apple."""
    pem = APNS_KEY.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    monkeypatch.setenv("APNS_KEY", pem.decode())
    monkeypatch.setenv("APNS_KEY_ID", "KEY1234567")
    monkeypatch.setenv("APNS_TEAM_ID", "TEAM123456")
    monkeypatch.setenv("APNS_BUNDLE_ID", "com.datingcrm.app")
    monkeypatch.delenv("APNS_SANDBOX", raising=False)
    stub = StubApns()
    stub.key = APNS_KEY  # for checking the signature of a push
    monkeypatch.setattr("app.push.post", stub)
    return stub
