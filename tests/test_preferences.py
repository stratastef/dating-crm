from sqlalchemy import text

from app.preferences import current_preferences

EMPTY = {"version": 0, "wishes": "", "must_haves": [], "dealbreakers": []}
FIRST = {"wishes": "Someone curious who laughs easily.", "must_haves": ["wants kids"], "dealbreakers": ["smokes"]}


def test_preferences_are_stored_and_returned_per_user(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")

    saved = alice.put("/preferences", json=FIRST)

    assert saved.status_code == 200
    assert saved.json() == {"version": 1, **FIRST}
    assert alice.get("/preferences").json() == {"version": 1, **FIRST}
    assert bob.get("/preferences").json() == EMPTY


def test_each_change_is_a_new_version_and_earlier_versions_stay_readable(client):
    second = {"wishes": "Curious, kind, outdoorsy.", "must_haves": ["wants kids", "lives nearby"], "dealbreakers": []}
    client.put("/preferences", json=FIRST)

    assert client.put("/preferences", json=second).json() == {"version": 2, **second}

    assert client.get("/preferences").json() == {"version": 2, **second}
    versions = client.get("/preferences/versions").json()
    assert [{key: value for key, value in version.items() if key != "created_at"} for version in versions] == [
        {"version": 1, **FIRST},
        {"version": 2, **second},
    ]
    assert all(version["created_at"] for version in versions)  # when each one came into force


def test_other_users_versions_are_not_listed(client_for):
    client_for("alice@example.com").put("/preferences", json=FIRST)

    assert client_for("bob@example.com").get("/preferences/versions").json() == []


def test_server_code_reads_the_version_in_force_with_one_function(app, client):
    client.put("/preferences", json=FIRST)
    client.put("/preferences", json={**FIRST, "dealbreakers": ["smokes", "no pets"]})

    with app.state.engine.connect() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        current = current_preferences(db, user_id)

    assert current.version == 2
    assert current.wishes == FIRST["wishes"]
    assert current.must_haves == ["wants kids"]
    assert current.dealbreakers == ["smokes", "no pets"]
