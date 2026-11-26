from tests.test_calendar import connect
from tests.test_tinder import submit_token


def done(client) -> dict[str, bool]:
    steps = client.get("/setup").json()
    return {step["step"]: step["done"] for step in steps}


def test_the_dating_apps_step_is_done_once_an_app_is_connected(client):
    assert done(client)["dating_apps"] is False

    assert submit_token(client).status_code == 204

    assert done(client)["dating_apps"] is True


def test_choosing_copilot_only_for_every_dating_app_counts_as_the_dating_apps_step_done(client):
    # Tinder is the only app with a connector: the others are copilot-only already, with nothing to choose.
    assert [app["state"] for app in client.get("/connectors").json()] == ["not_connected", "no_connector", "no_connector"]

    assert client.put("/connectors/tinder/copilot-only").status_code == 204

    assert done(client)["dating_apps"] is True


def test_the_calendar_step_is_done_once_google_calendar_is_connected(app, client):
    assert done(client)["calendar"] is False

    connect(client, app)

    assert done(client)["calendar"] is True


def test_the_voice_step_is_done_once_the_voice_questionnaire_is_answered(client):
    assert done(client)["voice"] is False
    client.put("/voice/questionnaire", json={"answers": {}})
    assert done(client)["voice"] is False  # saved, but nothing answered

    client.put("/voice/questionnaire", json={"answers": {"Do you send short messages or longer ones?": "Short."}})

    assert done(client)["voice"] is True


def test_the_preferences_step_is_done_once_preferences_are_saved(client):
    assert done(client)["preferences"] is False

    client.put("/preferences", json={"wishes": "Someone curious.", "must_haves": [], "dealbreakers": ["smokes"]})

    assert done(client)["preferences"] is True


def test_the_swipe_layout_and_autonomy_step_is_done_once_both_are_chosen(client_for):
    layout_first = client_for("alice@example.com")
    autonomy_first = client_for("bob@example.com")
    assert done(layout_first)["swipe_layout_and_autonomy"] is False

    layout_first.put("/swipes/layout", json={"layout": "list"})
    autonomy_first.put("/autonomy/chat", json={"level": "copilot"})  # the default, but now chosen

    assert done(layout_first)["swipe_layout_and_autonomy"] is False
    assert done(autonomy_first)["swipe_layout_and_autonomy"] is False

    layout_first.put("/autonomy/swipe", json={"level": "copilot"})
    autonomy_first.put("/swipes/layout", json={"layout": "one_at_a_time"})

    assert done(layout_first)["swipe_layout_and_autonomy"] is True
    assert done(autonomy_first)["swipe_layout_and_autonomy"] is True


def test_todays_setup_summary_counts_the_steps_left(client):
    assert client.get("/today").json()["setup"] == {"steps_left": 5}

    client.put("/preferences", json={"wishes": "Someone curious.", "must_haves": [], "dealbreakers": []})
    client.put("/connectors/tinder/copilot-only")

    assert client.get("/today").json()["setup"] == {"steps_left": 3}


def test_todays_setup_summary_disappears_once_setup_is_dismissed(client):
    assert client.patch("/settings", json={"setup_dismissed": True}).json()["setup_dismissed"] is True

    assert client.get("/today").json()["setup"] is None
    assert client.get("/settings").json()["setup_dismissed"] is True
    assert done(client)["calendar"] is False  # the steps stay as they are, under You


def test_todays_setup_summary_disappears_once_no_step_is_left(app, client):
    submit_token(client)
    connect(client, app)
    client.put("/voice/questionnaire", json={"answers": {"Do you send short messages or longer ones?": "Short."}})
    client.put("/preferences", json={"wishes": "Someone curious.", "must_haves": [], "dealbreakers": []})
    client.put("/swipes/layout", json={"layout": "list"})
    client.put("/autonomy/chat", json={"level": "copilot"})

    assert all(done(client).values())
    assert client.get("/today").json()["setup"] is None
