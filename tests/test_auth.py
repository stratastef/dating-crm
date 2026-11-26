import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import CurrentUser, Db
from app.tenancy import user_id_column


def test_request_without_credentials_is_rejected(app):
    response = TestClient(app).get("/me")

    assert response.status_code == 401


def test_request_with_an_unknown_token_is_rejected(app, client):
    response = TestClient(app).get("/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_authenticated_user_is_identified(client):
    response = client.get("/me")

    assert response.status_code == 200
    assert response.json() == {"email": "user@example.com"}


@pytest.fixture
def notes_app(app):
    """The app plus a throwaway tenant table and route, built the way real ones should be."""
    with app.state.engine.begin() as connection:
        op = Operations(MigrationContext.configure(connection))
        op.create_table("notes", user_id_column(), sa.Column("body", sa.Text, nullable=False))

    @app.post("/notes")
    def add_note(body: str, user: CurrentUser, db: Db) -> None:
        db.execute(text("INSERT INTO notes (user_id, body) VALUES (:user_id, :body)"), {"user_id": user.id, "body": body})

    @app.get("/notes")
    def list_notes(user: CurrentUser, db: Db) -> list[str]:
        rows = db.execute(text("SELECT body FROM notes WHERE user_id = :user_id"), {"user_id": user.id})
        return [row.body for row in rows]

    yield app
    with app.state.engine.begin() as connection:
        connection.execute(text("DROP TABLE notes"))


def test_one_user_cannot_read_another_users_rows(notes_app, client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    alice.post("/notes", params={"body": "alice's secret"})
    bob.post("/notes", params={"body": "bob's note"})

    assert alice.get("/notes").json() == ["alice's secret"]
    assert bob.get("/notes").json() == ["bob's note"]


def test_every_table_except_users_carries_a_user_id(app):
    # Invite codes belong to no user: one creates a user.
    with app.state.engine.connect() as connection:
        missing = connection.execute(
            text(
                """
                SELECT table_name FROM information_schema.tables t
                WHERE table_schema = 'public' AND table_name NOT IN ('users', 'alembic_version', 'invite_codes')
                  AND NOT EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema = t.table_schema AND c.table_name = t.table_name
                      AND c.column_name = 'user_id'
                  )
                """
            )
        ).scalars().all()

    assert missing == []
