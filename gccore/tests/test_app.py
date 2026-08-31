from fastapi.testclient import TestClient

from gccore.app import app


def test_root_reports_service_identity() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "gccore", "schema": "gc_core"}


def test_authorize_accepts_mock_null_client_id() -> None:
    client = TestClient(app)

    response = client.post("/authorize", json={"client_id": None})

    assert response.status_code == 200
    assert response.json() == {"authorized": True, "client_id": None}
