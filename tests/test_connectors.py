import pytest
from sqlalchemy import text

from app.connectors import CapabilityFailed, CapabilityUnavailable, Connector, alerts, call, is_copilot_only


class FakeConnector(Connector):
    """Supports every capability, in memory. `broken` names capabilities that raise."""

    app = "fake"
    capabilities = frozenset({"read_matches", "read_messages", "send", "like", "pass"})

    def __init__(self, broken=()):
        self.broken = set(broken)
        self.sent, self.liked, self.passed = [], [], []

    def _check(self, capability):
        if capability in self.broken:
            raise RuntimeError(f"{capability} is down")

    def read_matches(self, token):
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
    return db.execute(text("SELECT id FROM users")).scalar_one()


def test_every_declared_capability_can_be_called(db, user_id):
    fake = FakeConnector()

    assert call(db, user_id, fake, "read_matches", "token") == [{"id": "m1", "name": "Sam"}]
    assert call(db, user_id, fake, "read_messages", "token", "m1") == [{"match_id": "m1", "text": "hi"}]
    call(db, user_id, fake, "send", "token", "m1", "hello")
    call(db, user_id, fake, "like", "token", "p1")
    call(db, user_id, fake, "pass", "token", "p2")

    assert fake.sent == [("m1", "hello")]
    assert fake.liked == ["p1"]
    assert fake.passed == ["p2"]
    assert not is_copilot_only(db, user_id, "fake")


def test_a_capability_left_out_of_a_build_is_unavailable(db, user_id):
    class ReadOnly(FakeConnector):
        capabilities = frozenset({"read_matches", "read_messages"})

    fake = ReadOnly()

    assert call(db, user_id, fake, "read_matches", "token")
    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "send", "token", "m1", "hello")
    assert fake.sent == []
    assert not is_copilot_only(db, user_id, "fake")


def test_a_capability_disabled_by_configuration_is_unavailable(db, user_id, monkeypatch):
    monkeypatch.setenv("CONNECTOR_DISABLED_CAPABILITIES", "tinder:send, fake:like")
    fake = FakeConnector()

    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "like", "token", "p1")
    call(db, user_id, fake, "send", "token", "m1", "hello")

    assert fake.liked == []
    assert fake.sent == [("m1", "hello")]
    assert not is_copilot_only(db, user_id, "fake")


def test_a_failing_capability_makes_the_app_copilot_only_and_raises_an_alert(db, user_id):
    fake = FakeConnector(broken={"send"})

    with pytest.raises(CapabilityFailed) as failure:
        call(db, user_id, fake, "send", "token", "m1", "hello")

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert is_copilot_only(db, user_id, "fake")
    [alert] = alerts(db, user_id)
    assert (alert.app, alert.capability) == ("fake", "send")
    assert "send is down" in alert.error
    # Working capabilities stop too: the whole app is on copilot.
    with pytest.raises(CapabilityUnavailable):
        call(db, user_id, fake, "read_matches", "token")
    assert len(alerts(db, user_id)) == 1


def test_fallback_survives_the_callers_rollback(app, client):
    with app.state.engine.connect() as db:
        user_id = db.execute(text("SELECT id FROM users")).scalar_one()
        with pytest.raises(CapabilityFailed):
            call(db, user_id, FakeConnector(broken={"like"}), "like", "token", "p1")
        db.rollback()

    with app.state.engine.connect() as db:
        assert is_copilot_only(db, user_id, "fake")


def test_fallback_is_per_user_and_per_app(app, client_for):
    client_for("alice@example.com")
    client_for("bob@example.com")
    with app.state.engine.begin() as db:
        alice, bob = db.execute(text("SELECT id FROM users ORDER BY email")).scalars()
        with pytest.raises(CapabilityFailed):
            call(db, alice, FakeConnector(broken={"read_matches"}), "read_matches", "token")

        assert is_copilot_only(db, alice, "fake")
        assert not is_copilot_only(db, alice, "tinder")
        assert not is_copilot_only(db, bob, "fake")
        assert alerts(db, bob) == []
