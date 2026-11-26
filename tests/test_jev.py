import json
from datetime import UTC, datetime

import httpx
import pytest

from app import jev as jev_module
from app.cards import upsert_card, upsert_message
from app.jev import ask as real_ask  # imported before the autouse stub replaces it
from tests.test_drafts import drafted, write_profile


@pytest.fixture
def me(app, client):
    """`(db, user_id)` of the test user: every check is made for a user, under their AI budget."""
    with app.state.engine.begin() as db:
        yield db, db.exec_driver_sql("SELECT id FROM users").scalar_one()


@pytest.fixture
def real_jev(monkeypatch):
    """The real `ask`, configured, with the network replaced: `real_jev(p)` makes Jev answer probability `p`."""
    monkeypatch.setattr("app.jev.ask", real_ask)
    monkeypatch.setenv("JEV_BASE_URL", "https://treg.example")
    monkeypatch.setenv("JEV_API_KEY", "secret")
    monkeypatch.setenv("JEV_TOOL", "openrouter.ai-judge.decide")
    seen = []

    def use(probability):
        def handle(request):
            seen.append(request)
            return httpx.Response(200, json={"result": {"answers": {"q1": {"noul": probability}}}})

        monkeypatch.setattr("app.jev.transport", httpx.MockTransport(handle))
        return seen

    return use


def test_a_check_sends_one_sentence_to_jev_and_returns_yes_or_no(real_jev):
    seen = real_jev(0.93)
    assert jev_module.ask("I am definitely not a bot.", "denies_ai") is True
    request = seen[0]
    assert str(request.url) == "https://treg.example/call/openrouter.ai-judge.decide"
    assert request.headers["X-Treg-Token"] == "secret"
    assert "I am definitely not a bot." in json.loads(request.content)["state"]

    real_jev(0.07)
    assert jev_module.ask("I like climbing.", "denies_ai") is False


def test_the_protected_trait_guardrail_asks_jev_about_every_trait_the_spec_names(real_jev):
    seen = real_jev(0.1)

    jev_module.ask("Who did you vote for?", "protected_trait")

    statement = json.loads(seen[0].content)["questions"]["q1"]["criteria"]["true"]
    for trait in ("ethnicity", "religion", "health", "sexual", "politic"):
        assert trait in statement


def test_an_unknown_check_name_is_refused(real_jev):
    real_jev(0.9)
    with pytest.raises(KeyError):
        jev_module.ask("hello", "no_such_check")


@pytest.mark.parametrize(
    ("check", "phrase", "message"),
    [
        ("denies_ai", "not a bot", "Ha, good one. I am not a bot, promise."),
        ("protected_trait", "your religion", "Fun! Does your religion allow that?"),
        ("overpromise", "always", "Sure. I will always be there for you."),
    ],
)
def test_the_draft_guardrail_names_each_category_an_outgoing_message_hits(jev, me, check, phrase, message):
    jev.yes[check] = [phrase]

    assert jev_module.guardrail_hits(*me, message) == [check]
    assert jev_module.guardrail_hits(*me, "See you at the wall.") == []
    # Jev judged one sentence at a time, never the whole message.
    assert all(sentence != message for sentence, _ in jev.asked)


@pytest.mark.parametrize(
    ("check", "phrase", "message"),
    [
        ("asks_if_ai", "are you a bot", "Wait. Are you a bot?"),
        ("logistics", "saturday", "Sounds fun! Saturday at 8 at Bar Luna?"),
        ("personal_info", "my number", "Text me. My number is 555 0100."),
        ("sensitive", "my ex", "Honestly? My ex hit me."),
    ],
)
def test_the_handover_trigger_names_each_category_an_incoming_message_hits(jev, me, check, phrase, message):
    jev.yes[check] = [phrase]

    assert jev_module.handover_hits(*me, message) == [check]
    assert jev_module.handover_hits(*me, "do you climb outdoors too") == []


def test_hot_lead_triage_answers_yes_or_no_for_a_draft(jev, me):
    jev.yes["hot_lead"] = ["thursday"]

    assert jev_module.is_hot_lead(*me, "Yes! Thursday works, shall I book it?") is True
    assert jev_module.is_hot_lead(*me, "haha same") is False


def test_without_jev_configured_the_guardrail_and_handover_hit_and_triage_says_no(monkeypatch, me):
    monkeypatch.setattr("app.jev.ask", real_ask)
    for name in ("JEV_BASE_URL", "JEV_API_KEY", "JEV_TOOL"):
        monkeypatch.delenv(name, raising=False)

    assert jev_module.guardrail_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.handover_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.is_hot_lead(*me, "hello there") is False


def test_a_failing_jev_counts_as_a_hit(real_jev, monkeypatch, me):
    real_jev(0.0)
    monkeypatch.setattr("app.jev.transport", httpx.MockTransport(lambda request: httpx.Response(500)))

    assert jev_module.guardrail_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.handover_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.is_hot_lead(*me, "hello there") is False


@pytest.fixture
def model_jev(monkeypatch, llm):
    """The checks answered by the default model (`JEV_PROVIDER=llm`): `llm.reply` is the model's answer."""
    monkeypatch.setenv("JEV_PROVIDER", "llm")
    return llm


def test_the_demo_provider_asks_every_check_of_a_message_in_one_model_call(model_jev, jev, me):
    # Two sentences times the four guardrail checks: items 1 and 2 are `denies_ai` for each sentence.
    model_jev.reply = (
        'Here you go:\n```json\n{"1": true, "2": false, "3": false, "4": false, "5": false, "6": false, "7": false,'
        ' "8": false}\n```'
    )

    assert jev_module.guardrail_hits(*me, "I'm a real <human>. Promise.") == ["denies_ai"]

    assert len(model_jev.prompts) == 1
    assert "<sentence>I'm a real &lt;human&gt;.</sentence>" in model_jev.prompts[0]
    assert jev_module.CHECKS["denies_ai"] in model_jev.prompts[0]
    assert jev.asked == []  # treg's Jev is never asked
    db, _ = me
    assert db.exec_driver_sql("SELECT purpose FROM llm_calls").scalars().all() == ["jev"]


@pytest.mark.parametrize(
    "reply",
    ["no idea", '{"1": false}', '{"1": "no", "2": "no", "3": "no", "4": "no", "5": "no"}'],
    ids=["not json", "verdict missing", "verdict not a boolean"],
)
def test_the_demo_provider_fails_closed_on_an_answer_it_cannot_read(model_jev, me, reply):
    model_jev.reply = reply

    assert jev_module.guardrail_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.handover_hits(*me, "hello there") == ["unavailable"]
    assert jev_module.is_hot_lead(*me, "hello there") is False


def test_an_incoming_message_is_stored_with_its_handover_result(app, client, jev):
    jev.yes["logistics"] = ["saturday"]
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]

    hit = client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "Saturday at 8?"})
    client.post(f"/cards/{card_id}/messages", json={"sender": "them", "body": "or not"})
    asked = len(jev.asked)
    client.post(f"/cards/{card_id}/messages", json={"sender": "me", "body": "saturday works"})

    assert hit.json()["handover"] == ["logistics"]
    assert len(jev.asked) == asked  # the handover trigger is for incoming messages only
    stored = client.get(f"/cards/{card_id}/messages").json()
    assert [message["handover"] for message in stored] == [["logistics"], [], None]


def test_a_synced_incoming_message_is_checked_once_and_stored_with_its_result(app, client, jev):
    jev.yes["asks_if_ai"] = ["are you real"]
    client.get("/cards")
    with app.state.engine.begin() as db:
        user_id = db.exec_driver_sql("SELECT id FROM users").scalar_one()
        card_id = upsert_card(db, user_id, "tinder", "match-1", "Sam")
        now = datetime.now(UTC)
        upsert_message(db, user_id, card_id, "m1", "them", "are you real", now)
        asked = len(jev.asked)
        upsert_message(db, user_id, card_id, "m1", "them", "are you real", now)

    assert len(jev.asked) == asked  # a message already stored is not sent to Jev again
    assert client.get(f"/cards/{card_id}/messages").json()[0]["handover"] == ["asks_if_ai"]


def test_a_draft_is_stored_with_its_guardrail_and_hot_lead_results(app, client, llm, jev):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    jev.yes = {"overpromise": ["best night"], "hot_lead": ["thursday"]}

    llm.reply = drafted("thursday then. it will be the best night of your life")
    draft = client.post(f"/cards/{card_id}/drafts").json()

    assert draft["guardrail"] == ["overpromise"]
    assert draft["hot_lead"] is True


def test_editing_a_draft_runs_the_guardrail_on_the_edit(app, client, llm, jev):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]
    jev.yes["denies_ai"] = ["not a bot"]
    llm.reply = drafted("thursday then")
    draft = client.post(f"/cards/{card_id}/drafts").json()
    assert draft["guardrail"] == []

    edited = client.patch(f"/drafts/{draft['id']}", json={"edited": "i am not a bot. thursday then"}).json()

    assert edited["guardrail"] == ["denies_ai"]


def test_a_draft_jev_calls_a_hot_lead_is_pushed_at_once_and_is_hot_in_the_review_queue(app, client, llm, jev, apns):
    write_profile(app, client, llm, "Short, lowercase, teasing.")
    client.post("/devices", json={"token": "abc123"})
    card_id = client.post("/cards", json={"app": "hinge", "name": "Sam"}).json()["id"]  # no recent reply
    jev.yes["hot_lead"] = ["thursday"]

    llm.reply = drafted("thursday then")
    client.post(f"/cards/{card_id}/drafts")

    assert len(apns.sent) == 1
    assert [item["hot"] for item in client.get("/queue").json()] == [True]
