from decimal import Decimal

from sqlalchemy import text

from app import llm as claude
from app.jobs import run_once


def spend(app, email):
    with app.state.engine.connect() as db:
        user_id = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar_one()
        return claude.spend(db, user_id)


def test_every_model_call_records_its_cost_for_the_user_it_was_made_for(app, client_for, llm, monkeypatch):
    # The stub answers as model "stub" with 1 input and 1 output token.
    monkeypatch.setitem(claude.PRICES, "stub", (Decimal(3), Decimal(15)))  # USD per million tokens
    alice = client_for("alice@example.com")
    client_for("bob@example.com")

    alice.put("/voice/questionnaire", json={"answers": {"Emoji?": "Never"}})
    while run_once(app.state.engine):  # the voice job calls Claude once
        pass
    llm.reply = '{"bio": "climbs things.", "prompts": {}}'
    alice.post("/bios/hinge/rewrite", json={"bio": "I like climbing."})  # and the rewrite once more

    assert spend(app, "alice@example.com") == Decimal("0.000036")
    assert spend(app, "bob@example.com") == 0


def test_a_free_openrouter_model_costs_nothing(app, client_for, monkeypatch):
    reply = claude.Completion(text='{"bio": "x", "prompts": {}}', model="vendor/model:free", input_tokens=1000, output_tokens=1000)
    monkeypatch.setattr(claude, "complete", lambda *args, **kwargs: reply)
    alice = client_for("alice@example.com")
    alice.post("/bios/hinge/rewrite", json={"bio": "I like climbing."})

    assert spend(app, "alice@example.com") == 0
