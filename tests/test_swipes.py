"""Swipe copilot on Tinder, against the hand-written fixtures in `tests/fixtures/tinder`. No live calls."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.connectors import call
from app.tinder import TinderConnector
from app.vault import store_token

FIXTURES = Path(__file__).parent / "fixtures" / "tinder"
TOKEN = "tinder-session-secret"
DANA, EVE, FAY = "5f00000000000000000000d4", "5f00000000000000000000e5", "5f00000000000000000000f6"


class StubTinder:
    """Stands in for api.gotinder.com: serves candidates and accepts likes and passes. `status` forces an error."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.super_like = "super_like"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.headers.get("X-Auth-Token") != TOKEN:
            return self._fixture("unauthorized", 401)
        if self.status != 200:
            return httpx.Response(self.status, json={"meta": {"status": self.status}})
        kind = request.url.path.split("/")[1]
        if request.url.path == "/v2/recs/core":
            return self._fixture("recs")
        if request.method == "POST":  # the paid items; `super_like` names the fixture a Super Like answers with
            paid = {"boost": "boost", "like": self.super_like}.get(kind)
            if paid and request.url.path.endswith(("/boost", "/super")):
                return self._fixture(paid)
        elif kind in ("like", "pass"):
            return self._fixture(kind)
        return httpx.Response(404, json={"meta": {"status": 404}})

    def _fixture(self, name: str, status: int = 200) -> httpx.Response:
        return httpx.Response(status, json=json.loads((FIXTURES / f"{name}.json").read_text()))

    def calls(self) -> list[str]:
        return [f"{request.method} {request.url.path}" for request in self.requests]


@pytest.fixture
def tinder(monkeypatch):
    stub = StubTinder()
    monkeypatch.setattr(TinderConnector, "transport", httpx.MockTransport(stub))
    return stub


@pytest.fixture
def db(app, client):
    with app.state.engine.begin() as connection:
        yield connection


@pytest.fixture
def user_id(db):
    user_id = db.execute(text("SELECT id FROM users")).scalar_one()
    store_token(db, user_id, "tinder", TOKEN)
    return user_id


def test_read_candidates_returns_each_profile_with_its_bio_photos_age_and_distance(db, user_id, tinder):
    candidates = call(db, user_id, TinderConnector(), "read_candidates")
    born_on_new_year = date.today().year  # every fixture birthday is January 1st

    assert candidates == [
        {
            "id": DANA,
            "name": "Dana",
            "bio": "Coffee first. I smoke a pack a day and love it.",
            "photos": ["https://images-ssl.gotinder.com/5f00000000000000000000d4/p-d4-1.jpg"],
            "age": born_on_new_year - 1994,
            "distance_mi": 3,
        },
        {
            "id": EVE,
            "name": "Eve",
            "bio": "Climber. Looking for someone to share long hikes with.",
            "photos": [
                "https://images-ssl.gotinder.com/5f00000000000000000000e5/p-e5-1.jpg",
                "https://images-ssl.gotinder.com/5f00000000000000000000e5/p-e5-2.jpg",
            ],
            "age": born_on_new_year - 1996,
            "distance_mi": 5,
        },
        {"id": FAY, "name": "Fay", "bio": "", "photos": [], "age": born_on_new_year - 1993, "distance_mi": 8},
    ]


def test_like_and_pass_reach_tinder_and_never_the_paid_super_like(db, user_id, tinder):
    call(db, user_id, TinderConnector(), "like", EVE)
    call(db, user_id, TinderConnector(), "pass", DANA)

    assert tinder.calls() == [f"GET /like/{EVE}", f"GET /pass/{DANA}"]


# Copilot: the token goes in through the API, the app suggests, and the user decides each one.


@pytest.fixture
def signed_in(client, tinder):
    """The user's client, with their Tinder token stored."""
    assert client.put("/connectors/tinder/token", json={"token": TOKEN}).status_code == 204
    return client


def suggestions(client) -> dict[str, dict]:
    response = client.post("/swipes/tinder/suggestions")
    assert response.status_code == 200, response.text
    return {candidate["name"]: candidate for candidate in response.json()}


def test_a_purged_candidate_is_not_stored_again_when_the_app_offers_the_profile_again(signed_in, llm):
    llm.reply = "like\nShe climbs."
    dana = suggestions(signed_in)["Dana"]

    assert signed_in.post("/people/purge", json={"candidate_ids": [dana["id"]], "confirm": "purge"}).status_code == 200

    assert "Dana" not in suggestions(signed_in)
    assert signed_in.get("/people/candidates", params={"q": "Dana"}).json() == []


def test_a_dealbreaker_in_the_bio_is_a_pass_with_no_claude_call_and_no_photo_analysis(signed_in, tinder, jev, llm):
    signed_in.put("/preferences", json={"dealbreakers": ["smokes"]})
    jev.yes["dealbreaker"] = ["smoke"]
    llm.reply = "like\nShe climbs."

    dana = suggestions(signed_in)["Dana"]

    assert (dana["suggestion"], dana["source"], dana["reason"]) == ("pass", "jev", "Dealbreaker: smokes")
    assert ("I smoke a pack a day and love it.", "dealbreaker") in jev.asked
    # Claude saw the other two profiles only, and never a photo; Tinder was asked for the candidates and nothing else.
    assert len(llm.prompts) == 2
    assert not any("Dana" in prompt or "gotinder.com" in prompt for prompt in llm.prompts)
    assert tinder.calls() == ["GET /v2/recs/core"]


def test_the_cheap_model_pre_screens_the_other_profiles_and_its_cost_is_recorded(signed_in, llm):
    signed_in.put("/preferences", json={"wishes": "outdoorsy and kind", "must_haves": ["wants kids"]})
    llm.reply = "like\nShe hikes and climbs."

    eve = suggestions(signed_in)["Eve"]

    assert (eve["suggestion"], eve["source"], eve["reason"]) == ("like", "model", "She hikes and climbs.")
    assert eve["decision"] is None
    assert eve["photos"][0].endswith("p-e5-1.jpg")  # shown to the user, never analysed
    assert llm.models == ["claude-haiku-5-5"] * 3
    prompt = next(prompt for prompt in llm.prompts if "Eve" in prompt)
    assert "outdoorsy and kind" in prompt and "wants kids" in prompt and "share long hikes" in prompt
    assert signed_in.get("/budget").json()["spend_usd"] > 0


def test_the_pre_screen_model_is_read_from_the_environment(signed_in, llm, monkeypatch):
    monkeypatch.setenv("SWIPE_PRESCREEN_MODEL", "claude-sonnet-5-5")
    llm.reply = "pass\nNo shared interests."

    assert suggestions(signed_in)["Eve"]["suggestion"] == "pass"
    assert set(llm.models) == {"claude-sonnet-5-5"}


def test_a_profile_is_screened_once_and_waits_until_the_user_decides(signed_in, llm):
    llm.reply = "like\nWhy not."
    first = suggestions(signed_in)

    again = suggestions(signed_in)

    assert again == first and len(llm.prompts) == 3
    assert signed_in.get("/swipes", params={"app": "tinder"}).json() == list(first.values())


def test_at_the_ai_budget_nothing_is_screened_by_jev_or_by_the_model(signed_in, jev, llm):
    signed_in.put("/preferences", json={"dealbreakers": ["smokes"]})
    jev.yes["dealbreaker"] = ["smoke"]
    signed_in.put("/budget", json={"cap_usd": 0})

    assert list(suggestions(signed_in)) == []
    assert llm.prompts == [] and jev.asked == []


def test_an_answer_that_is_neither_like_nor_pass_suggests_nothing(signed_in, llm):
    llm.reply = "I cannot tell."

    assert suggestions(signed_in) == {}


def test_a_candidate_shows_age_distance_and_the_super_like_proposed_for_them_while_it_waits(signed_in, llm):
    llm.replies = ["pass\nNothing in common.", "super like\nShe climbs."]  # Dana, then Eve

    found = suggestions(signed_in)

    eve = found["Eve"]
    assert (eve["age"], eve["distance_mi"]) == (date.today().year - 1996, 5)
    assert eve["paid_item"] == {
        "id": eve["paid_item"]["id"],
        "app": "tinder",
        "item": "super_like",
        "name": "Eve",
        "reason": "She climbs.",
        "status": "pending",
    }
    assert found["Dana"]["paid_item"] is None
    signed_in.post(f"/paid-items/{eve['paid_item']['id']}/decline")
    assert [candidate["paid_item"] for candidate in signed_in.get("/swipes").json()] == [None, None]  # Dana, Eve


def test_suggestions_need_a_stored_token_and_a_known_app(client, tinder):
    assert client.post("/swipes/tinder/suggestions").status_code == 409
    assert client.post("/swipes/hinge/suggestions").status_code == 404
    assert tinder.requests == []


def decide(client, candidate: dict, decision: str):
    return client.post(f"/swipes/{candidate['id']}/decision", json={"decision": decision})


def test_confirming_a_like_swipes_in_tinder_and_stores_the_swipe(signed_in, tinder, llm):
    llm.reply = "like\nShe climbs."
    eve = suggestions(signed_in)["Eve"]

    response = decide(signed_in, eve, "like")

    assert response.status_code == 200, response.text
    assert response.json() == eve | {"decision": "like", "applied": True}
    assert tinder.calls()[-1] == f"GET /like/{EVE}"
    assert "Eve" not in [candidate["name"] for candidate in signed_in.get("/swipes").json()]
    assert decide(signed_in, eve, "pass").status_code == 409  # one swipe per profile


def test_overriding_a_suggestion_passes_in_tinder_and_keeps_both_the_suggestion_and_the_swipe(signed_in, tinder, llm):
    llm.reply = "like\nShe climbs."
    eve = suggestions(signed_in)["Eve"]

    swipe = decide(signed_in, eve, "pass").json()

    assert (swipe["suggestion"], swipe["decision"], swipe["applied"]) == ("like", "pass", True)
    assert tinder.calls()[-1] == f"GET /pass/{EVE}"


def test_nothing_is_swiped_in_tinder_until_the_user_decides(signed_in, tinder, llm):
    llm.reply = "like\nShe climbs."

    suggestions(signed_in)

    assert tinder.calls() == ["GET /v2/recs/core"]


def test_when_tinder_refuses_the_swipe_it_is_still_stored_and_the_user_is_told(signed_in, tinder, llm):
    llm.reply = "like\nShe climbs."
    eve = suggestions(signed_in)["Eve"]
    tinder.status = 403

    swipe = decide(signed_in, eve, "like").json()

    assert (swipe["decision"], swipe["applied"]) == ("like", False)
    assert signed_in.get("/connectors/alerts").json()[0]["capability"] == "like"


def test_a_candidate_of_another_user_is_not_found(signed_in, client_for, llm):
    llm.reply = "like\nShe climbs."
    eve = suggestions(signed_in)["Eve"]

    assert decide(client_for("other@example.com"), eve, "like").status_code == 404
    assert decide(signed_in, eve, "maybe").status_code == 422


# Swipe layout (ADR 0004): the user picks one at a time or a list.


def test_the_swipe_layout_is_empty_until_the_user_chooses_and_reads_back_once_chosen(client):
    assert client.get("/swipes/layout").json() == {"layout": None}

    assert client.put("/swipes/layout", json={"layout": "list"}).json() == {"layout": "list"}
    assert client.get("/swipes/layout").json() == {"layout": "list"}
    assert client.put("/swipes/layout", json={"layout": "one_at_a_time"}).status_code == 200
    assert client.get("/swipes/layout").json() == {"layout": "one_at_a_time"}
    assert client.put("/swipes/layout", json={"layout": "grid"}).status_code == 422
    assert client.put("/swipes/layout", json={"layout": None}).status_code == 422
