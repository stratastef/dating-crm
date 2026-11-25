from fastapi.testclient import TestClient

from app.main import create_app


def test_health_is_ok_when_postgres_is_reachable():
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_unavailable_when_postgres_is_unreachable():
    # Port 1 on localhost refuses connections.
    app = create_app("postgresql+psycopg://app:app@127.0.0.1:1/app")

    response = TestClient(app).get("/health")

    assert response.status_code == 503
