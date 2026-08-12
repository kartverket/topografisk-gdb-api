from fastapi.testclient import TestClient

from gcjobs.app import app


def test_root_reports_service_identity() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "gcjobs", "schema": "gc_jobs"}