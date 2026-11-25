import httpx
import pytest
from sqlalchemy import text

from app.autopilot import autopilot_allowed, autopilot_block, set_autonomy
from app.connectors import CapabilityFailed, CapabilityUnavailable, Connector, alerts, call, is_copilot_only
from app.vault import delete_token, store_token


class FakeConnector(Connector):
    """Supports every capability, in memory. `broken` names capabilities the app refuses with HTTP 401."""

    app = "fake"
    capabilities = frozenset({"read_matches", "read_messages", "send", "like", "pass"})

    def __init__(self, broken=()):
        self.broken = set(broken)
        self.sent, self.liked, self.passed = [], [], []

    def _check(self, capability):
        if capability in self.broken:
            raise http_error(401)

    def read_matches(self, token):
        self.token = token
        self._check("read_matches")
        return [{"id": "m1", "name": "Sam"}]

    def read_messages(self, token, match_id):
        self._check("read_messages")
        return [{"match_id": match_id, "text": "hi"}]

    def send(self, token, match_id, text):
        self._check("send")
        self.sent.append((match_id, text))

    def like(self, token, profile_id):
        self._check("like")
        self.liked.append(profile_id)

    def pass_(self, token, profile_id):
        self._check("pass")
        self.passed.append(profile_id)


@pytest.fixture
def db(app, client):
    with app.state.engine.begin() as connection:
        yield connection


@pytest.fixture
def user_id(db):
    user_id = db.execute(text("SELECT id FROM users")).scalar_one()
    store_token(db, user_id, "fake", "fake-session")
    return user_id


def test_the_connector_gets_the_users_token_from_the_vault(db, user_id):
    fake = FakeConnector()

    call(db, user_id, fake, "read_matches")

    assert fake.token == "fake-session"


def test_without_a_stored_token_the_capability_is_unavailable(db, user_id):
    delete_token(db, user_id, "fake")

    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, FakeConnector(), "read_matches")
    assert not is_copilot_only(db, user_id, "fake")


def test_every_declared_capability_can_be_called(db, user_id):
    fake = FakeConnector()

    assert call(db, user_id, fake, "read_matches") == [{"id": "m1", "name": "Sam"}]
    assert call(db, user_id, fake, "read_messages", "m1") == [{"match_id": "m1", "text": "hi"}]
    call(db, user_id, fake, "send", "m1", "hello")
    call(db, user_id, fake, "like", "p1")
    call(db, user_id, fake, "pass", "p2")

    assert fake.sent == [("m1", "hello")]
    assert fake.liked == ["p1"]
    assert fake.passed == ["p2"]
    assert not is_copilot_only(db, user_id, "fake")


def test_a_capability_left_out_of_a_build_is_unavailable(db, user_id):
    class ReadOnly(FakeConnector):
        capabilities = frozenset({"read_matches", "read_messages"})

    fake = ReadOnly()

    assert call(db, user_id, fake, "read_matches")
    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "send", "m1", "hello")
    assert fake.sent == []
    assert not is_copilot_only(db, user_id, "fake")


def test_a_capability_disabled_by_configuration_is_unavailable(db, user_id, monkeypatch):
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send, fake:like")
    fake = FakeConnector()

    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "like", "p1")
    call(db, user_id, fake, "send", "m1", "hello")

    assert fake.liked == []
    assert fake.sent == [("m1", "hello")]
    assert not is_copilot_only(db, user_id, "fake")


def test_a_failing_capability_makes_the_app_copilot_only_and_raises_an_alert(db, user_id):
    fake = FakeConnector(broken={"send"})

    with pytest.raises(CapabilityFailed) as failure:
        call(db, user_id, fake, "send", "m1", "hello")

    assert isinstance(failure.value.__cause__, httpx.HTTPStatusError)
    assert is_copilot_only(db, user_id, "fake")
    [alert] = alerts(db, user_id)
    assert (alert.app, alert.capability) == ("fake", "send")
    assert alert.error == "HTTPStatusError 401"
    # Working capabilities stop too: the whole app is on copilot.
    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "read_matches")
    assert len(alerts(db, user_id)) == 1


def test_fallback_survives_the_callers_rollback(app, client):
    with app.state.engine.connect() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        store_token(db, user_id, "fake", "fake-session")
        with pytest.raises(CapabilityFailed):
            call(db, user_id, FakeConnector(broken={"like"}), "like", "p1")
        db.rollback()

    with app.state.engine.connect() as db:
        assert is_copilot_only(db, user_id, "fake")


def test_fallback_is_per_user_and_per_app(app, client_for):
    client_for("alice@example.com")
    client_for("bob@example.com")
    with app.state.engine.begin() as db:
        alice, bob = db.execute(text("SELECT id FROM users ORDER BY email")).scalars()
        store_token(db, alice, "fake", "fake-session")
        with pytest.raises(CapabilityFailed):
            call(db, alice, FakeConnector(broken={"read_matches"}), "read_matches")

        assert is_copilot_only(db, alice, "fake")
        assert not is_copilot_only(db, alice, "tinder")
        assert not is_copilot_only(db, bob, "fake")
        assert alerts(db, bob) == []


def http_error(status: int, url: str = "https://app.example/matches") -> httpx.HTTPStatusError:
    request = httpx.Request("GET", url)
    return httpx.HTTPStatusError(f"{status} for {url}", request=request, response=httpx.Response(status, request=request))


def test_a_stored_alert_holds_the_kind_of_error_and_no_match_or_profile_id(db, user_id):
    """An alert outlives a purge, so it must not name anyone: the app's URLs hold match and profile IDs."""
    error = http_error(403, "https://app.example/matches/match-771/messages")

    with pytest.raises(CapabilityFailed):
        call(db, user_id, RefusingConnector(error), "read_messages", "match-771")

    [alert] = alerts(db, user_id)
    assert alert.error == "HTTPStatusError 403"


class RefusingConnector(FakeConnector):
    """Every capability raises `error`."""

    def __init__(self, error: Exception):
        super().__init__()
        self.error = error

    def _check(self, capability):
        raise self.error


def test_a_ban_signal_pauses_that_apps_autopilot_and_the_alert_names_the_reason(db, user_id):
    set_autonomy(db, user_id, "chat", "full")

    with pytest.raises(CapabilityFailed):
        call(db, user_id, RefusingConnector(http_error(403)), "read_matches")

    assert autopilot_block(db, user_id, "fake", "chat") == "autopilot paused for fake: ban signal"
    assert autopilot_allowed(db, user_id, "tinder", "chat")
    [alert] = alerts(db, user_id)
    assert (alert.app, alert.reason) == ("fake", "ban signal")


@pytest.mark.parametrize("error", [http_error(500), http_error(429), httpx.ConnectTimeout("timed out"), RuntimeError("bug")])
def test_a_transient_error_neither_pauses_the_app_nor_makes_it_copilot_only(db, user_id, error, apns):
    set_autonomy(db, user_id, "chat", "full")

    with pytest.raises(CapabilityFailed):
        call(db, user_id, RefusingConnector(error), "read_matches")

    assert autopilot_allowed(db, user_id, "fake", "chat")
    assert not is_copilot_only(db, user_id, "fake")
    assert alerts(db, user_id) == []
    # The next attempt reaches the app again, with no token resubmitted: a job's retry can succeed.
    assert call(db, user_id, FakeConnector(), "read_matches") == [{"id": "m1", "name": "Sam"}]
