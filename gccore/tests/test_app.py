from fastapi.testclient import TestClient

from gccore.app import app


def test_root_reports_service_identity() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "gccore", "schema": "gc_core"}


def test_auth_reports_authorized_for_development() -> None:
    client = TestClient(app)

    response = client.get("/auth")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "authorized": True}
