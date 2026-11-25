import logging

import pytest
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, text

from app.auth import create_user
from app.db import database_url
from app.vault import delete_token, read_token, store_token


@pytest.fixture
def db(app):
    with app.state.engine.begin() as connection:
        yield connection


def user_id(db, email="user@example.com") -> int:
    create_user(db, email)
    return db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar_one()


def test_a_stored_token_can_be_read_back(db):
    user = user_id(db)

    store_token(db, user, "tinder", "tinder-session-secret")

    assert read_token(db, user, "tinder") == "tinder-session-secret"


def test_a_deleted_token_is_gone(db):
    user = user_id(db)
    store_token(db, user, "tinder", "tinder-session-secret")

    delete_token(db, user, "tinder")

    assert read_token(db, user, "tinder") is None


def test_tokens_are_kept_per_user_and_app(db):
    alice, bob = user_id(db, "alice@example.com"), user_id(db, "bob@example.com")
    store_token(db, alice, "tinder", "alice-tinder")
    store_token(db, alice, "hinge", "alice-hinge")
    store_token(db, bob, "tinder", "bob-tinder")
    store_token(db, bob, "tinder", "bob-tinder-renewed")

    assert read_token(db, alice, "tinder") == "alice-tinder"
    assert read_token(db, alice, "hinge") == "alice-hinge"
    assert read_token(db, bob, "tinder") == "bob-tinder-renewed"
    assert read_token(db, bob, "hinge") is None


def test_the_stored_value_is_not_the_plaintext(db):
    store_token(db, user_id(db), "tinder", "tinder-session-secret")

    dump = db.execute(text("SELECT string_agg(t::text, ' ') FROM session_tokens t")).scalar_one()
    assert "tinder" in dump  # the row is really there
    assert "tinder-session-secret" not in dump


def test_one_users_key_cannot_decrypt_another_users_token(db):
    alice, bob = user_id(db, "alice@example.com"), user_id(db, "bob@example.com")
    store_token(db, alice, "tinder", "alice-tinder")
    store_token(db, bob, "tinder", "bob-tinder")

    db.execute(
        text(
            "UPDATE session_tokens SET ciphertext = "
            "(SELECT ciphertext FROM session_tokens WHERE user_id = :alice) WHERE user_id = :bob"
        ),
        {"alice": alice, "bob": bob},
    )

    with pytest.raises(InvalidToken):
        read_token(db, bob, "tinder")


def test_tokens_cannot_be_read_with_a_different_master_key(db, monkeypatch):
    user = user_id(db)
    store_token(db, user, "tinder", "tinder-session-secret")

    monkeypatch.setenv("TOKEN_VAULT_MASTER_KEY", Fernet.generate_key().decode())

    with pytest.raises(InvalidToken):
        read_token(db, user, "tinder")


def test_the_vault_refuses_to_work_without_a_master_key_in_the_environment(db, monkeypatch):
    user = user_id(db)
    monkeypatch.delenv("TOKEN_VAULT_MASTER_KEY")

    with pytest.raises(KeyError, match="TOKEN_VAULT_MASTER_KEY"):
        store_token(db, user, "tinder", "tinder-session-secret")


def test_token_values_never_appear_in_logs(app, caplog):
    caplog.set_level(logging.DEBUG)
    # echo="debug" makes this engine log every statement, parameter and result row.
    engine = create_engine(database_url(), echo="debug")
    with engine.begin() as db:
        user = user_id(db)
        store_token(db, user, "tinder", "tinder-session-secret")
        assert read_token(db, user, "tinder") == "tinder-session-secret"
        delete_token(db, user, "tinder")
    engine.dispose()

    assert "INSERT INTO session_tokens" in caplog.text  # SQL logging was really on
    assert "tinder-session-secret" not in caplog.text
