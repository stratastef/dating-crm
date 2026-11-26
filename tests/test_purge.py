from sqlalchemy import text

from app import calendar
from app.audit import record_action
from tests.test_calendar import NINE, SEVEN, connect
from tests.test_drafts import drafted, write_profile
from tests.test_reads import inference, read


def new_card(client, app, name, external_id=None):
    return client.post("/cards", json={"app": app, "name": name, "external_id": external_id}).json()["id"]


def test_a_person_is_found_across_apps_by_name_or_handle(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    on_tinder = new_card(alice, "tinder", "Zelda Fitz", "zel_on_tinder")
    on_hinge = new_card(alice, "hinge", "zelda", "zf-hinge")
    new_card(alice, "tinder", "Sam", "sam1")
    new_card(bob, "tinder", "Zelda Fitz", "zel_on_tinder")

    def found(q):
        return [(card["id"], card["app"]) for card in alice.get("/people", params={"q": q}).json()]

    assert found("ZELDA") == [(on_tinder, "tinder"), (on_hinge, "hinge")]
    assert found("zf-hinge") == [(on_hinge, "hinge")]
    assert found("100%") == []  # the query is plain text, not a pattern
    assert alice.get("/people", params={"q": ""}).status_code == 422


def test_purge_removes_the_card_with_its_messages_photos_and_read(client, llm):
    zelda = new_card(client, "tinder", "Zelda")
    sam = new_card(client, "tinder", "Sam")
    for card_id in (zelda, sam):
        client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "hi"})
        client.post(f"/cards/{card_id}/photos", json={"url": "https://example.com/1.jpg"})
        read(client, llm, card_id, [inference("tone", "playful")])

    purged = client.post("/people/purge", json={"card_ids": [zelda], "confirm": "purge"})

    assert purged.status_code == 200
    assert purged.json() == {"purged": 1}
    assert client.get(f"/cards/{zelda}").status_code == 404
    assert client.get(f"/cards/{zelda}/messages").status_code == 404
    assert client.get(f"/cards/{zelda}/read").status_code == 404
    assert [card["id"] for card in client.get("/cards").json()] == [sam]
    assert len(client.get(f"/cards/{sam}/messages").json()) == 1
    assert len(client.get(f"/cards/{sam}/read").json()) == 1


def test_purge_needs_the_confirmation_value(client):
    zelda = new_card(client, "tinder", "Zelda")

    assert client.post("/people/purge", json={"card_ids": [zelda]}).status_code == 422
    assert client.post("/people/purge", json={"card_ids": [zelda], "confirm": "yes"}).status_code == 422
    assert client.post("/people/purge", json={"card_ids": [], "confirm": "purge"}).status_code == 422
    assert client.get(f"/cards/{zelda}").status_code == 200


def test_purge_is_all_or_nothing_and_only_for_the_callers_cards(client_for):
    alice = client_for("alice@example.com")
    bob = client_for("bob@example.com")
    hers = new_card(alice, "tinder", "Zelda")
    his = new_card(bob, "tinder", "Zelda")

    assert alice.post("/people/purge", json={"card_ids": [hers, his], "confirm": "purge"}).status_code == 404
    assert alice.get(f"/cards/{hers}").status_code == 200
    assert bob.get(f"/cards/{his}").status_code == 200


def test_purge_drops_audit_entries_about_the_person_and_logs_itself_without_their_content(app, client):
    zelda = new_card(client, "tinder", "Zelda Quixote", "zq-handle")
    new_card(client, "hinge", "Sam", "zq-handle")  # the same handle on another app is another person
    with app.state.engine.begin() as connection:
        user_id = connection.execute(text("SELECT id FROM users")).scalar_one()
        for app_name, target in [
            ("tinder", f"card:{zelda}"),
            ("tinder", f"card:{zelda} hold 2026-12-01T19:00:00+00:00"),
            ("tinder", "match:zq-handle"),
            ("hinge", "match:zq-handle"),
            ("tinder", f"card:{zelda}0"),  # another card whose id starts with the same digits
        ]:
            record_action(connection, user_id, type="message", app=app_name, target=target, trigger="chat autopilot")

    client.post("/people/purge", json={"card_ids": [zelda], "confirm": "purge"})

    log = [(entry["type"], entry["app"], entry["target"], entry["trigger"]) for entry in client.get("/audit-log").json()]
    assert log == [
        ("purge", "tinder", f"card:{zelda}", "deletion request"),
        ("message", "tinder", f"card:{zelda}0", "chat autopilot"),
        ("message", "hinge", "match:zq-handle", "chat autopilot"),
    ]


# Every table that references `cards`, directly or through another table, read from the foreign keys.
_CARD_TABLES = """
    WITH RECURSIVE linked(oid) AS (
        SELECT conrelid FROM pg_constraint WHERE contype = 'f' AND confrelid = 'cards'::regclass
        UNION
        SELECT c.conrelid FROM pg_constraint c JOIN linked ON c.confrelid = linked.oid WHERE c.contype = 'f'
    )
    SELECT oid::regclass::text FROM linked WHERE oid <> 'cards'::regclass
"""


def test_no_row_for_a_purged_person_remains_in_any_table(app, client, llm, gcal):
    """The tables are discovered, not listed. When this fails for a new table, seed a row for the person
    below (with `quixote` in its text), and make the purge remove it."""
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = new_card(client, "tinder", "Zelda Quixote", "quixote-771")
    client.patch(f"/cards/{card_id}", json={"notes": "quixote likes windmills", "date_note": "quixote was late"})
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "quixote here, come climb"})
    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "hi quixote"})
    client.post(f"/cards/{card_id}/photos", json={"url": "https://example.com/quixote.jpg"})
    read(client, llm, card_id, [inference("interests", "quixote: climbing")])
    llm.reply = drafted("quixote, saturday?")
    assert client.post(f"/cards/{card_id}/drafts").status_code == 201
    connect(client, app)

    def count(connection, table, where="true"):
        return connection.execute(text(f'SELECT count(*) FROM {table} AS r WHERE {where}')).scalar_one()

    def holding_her_content(connection):
        tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'")
        ).scalars()
        return {table for table in tables if count(connection, f'"{table}"', "r::text ILIKE '%quixote%'")}

    with app.state.engine.begin() as connection:
        user_id = connection.execute(text("SELECT id FROM users")).scalar_one()
        record_action(
            connection, user_id, type="message", app="tinder", target="match:quixote-771", trigger="chat autopilot"
        )
        calendar.hold_slot(connection, user_id, card_id, SEVEN, NINE, trigger="chat autopilot: proposed a time")
        calendar.hold_slot(connection, user_id, card_id, NINE, NINE + (NINE - SEVEN), trigger="chat autopilot")
        calendar.confirm_date(connection, user_id, card_id, trigger="match agreed", start=SEVEN)
        assert ["Date with Zelda Quixote"] == [event["summary"] for event in gcal.events.values()]
        card_tables = connection.execute(text(_CARD_TABLES)).scalars().all()
        unseeded = [table for table in card_tables if count(connection, table) == 0]
        assert not unseeded, f"these tables reference cards; seed a row for the person in this test: {unseeded}"
        assert {"cards", "messages", "card_photos", "inferences", "drafts", "audit_log"} <= holding_her_content(connection)

    assert client.post("/people/purge", json={"card_ids": [card_id], "confirm": "purge"}).status_code == 200

    with app.state.engine.begin() as connection:
        # She was the only person on file, so every card table must now be empty.
        assert {table: count(connection, table) for table in ["cards", *card_tables]} == dict.fromkeys(
            ["cards", *card_tables], 0
        )
        assert holding_her_content(connection) == set()
    assert gcal.events == {}  # her name was in the calendar event too
