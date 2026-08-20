import json as jsonlib
import logging

import httpx2
import pytest
from fastapi.testclient import TestClient

from gcjobs.app import create_app
from gcjobs.pubsub import StubImportEventListener


def test_root_reports_service_identity() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "gcjobs", "schema": "gc_jobs"}


def test_imports_preflight_allows_any_origin() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.options(
        "/imports",
        headers={
            "origin": "https://example.no",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_import_events_are_logged(caplog, monkeypatch: pytest.MonkeyPatch) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error.gcjobs.import_events")
    monkeypatch.setattr(
        "gcjobs.app.db.record_import_event",
        lambda event, *, message_id=None: {"id": event["import_id"]},
    )
    app = create_app(
        event_listener=StubImportEventListener(
            [{"event": "import.started", "import_id": "job-1", "profile": "fkb_bane"}]
        )
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert any("import.started" in message for message in caplog.messages)


def test_import_event_logs_hide_feature_ids(
    caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error.gcjobs.import_events")
    monkeypatch.setattr(
        "gcjobs.app.db.record_import_event",
        lambda event, *, message_id=None: {"id": event["import_id"]},
    )
    app = create_app(
        event_listener=StubImportEventListener(
            [
                {
                    "event": "import.batch.succeeded",
                    "import_id": "job-1",
                    "feature_ids": ["a", "b", "c"],
                }
            ]
        )
    )

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert any("feature_id_count" in message for message in caplog.messages)
    assert all("feature_ids" not in message for message in caplog.messages)


def test_import_event_listener_delegates_to_db(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[dict[str, str]] = []
    listener = StubImportEventListener(
        [{"import_id": "run-1", "event": "import.started"}]
    )

    def fake_record_import_event(event, *, message_id=None):
        recorded.append({**event, "message_id": message_id})
        return {"id": event["import_id"]}

    monkeypatch.setattr("gcjobs.app.db.record_import_event", fake_record_import_event)
    app = create_app(event_listener=listener)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert recorded == [
        {"import_id": "run-1", "event": "import.started", "message_id": None}
    ]
    assert listener.acked_events == [{"import_id": "run-1", "event": "import.started"}]


def test_import_current_endpoint_reads_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.list_import_runs",
        lambda *, active_only: [
            {"id": "run-1", "status": "running", "active_only": active_only}
        ],
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/imports/current")

    assert response.status_code == 200
    assert response.json() == {
        "imports": [{"id": "run-1", "status": "running", "active_only": True}]
    }


def test_import_events_history_404s_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gcjobs.app.db.get_import_run", lambda _import_id: None)
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/imports/missing/events")

    assert response.status_code == 404


def test_import_start_proxies_to_gcimport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    requests: list[httpx2.Request] = []
    recorded: list[dict[str, str]] = []

    def fake_record_import_event(event, *, message_id=None):
        recorded.append(event)
        return {"id": event["import_id"]}

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"total": 1, "features": []})

    monkeypatch.setattr("gcjobs.app.db.record_import_event", fake_record_import_event)
    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={
                "file": (
                    "source.geojson",
                    jsonlib.dumps({"type": "FeatureCollection", "features": []}),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 202
    assert response.json()["import_id"]
    assert response.json()["status"] == "accepted"
    assert requests[0].url == "http://gcimport:8000/imports?profile=fkb_bane"
    assert requests[0].headers["x-import-id"] == response.json()["import_id"]
    assert recorded == [
        {
            "import_id": response.json()["import_id"],
            "event": "import.accepted",
            "phase": "accepted",
            "profile": "fkb_bane",
        }
    ]


def test_import_start_records_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    recorded: list[dict[str, str]] = []

    def fake_record_import_event(event, *, message_id=None):
        recorded.append(event)
        return {"id": event["import_id"]}

    def fake_get_import_run(_import_id):
        if not recorded:
            return None
        if recorded[-1]["event"] == "import.completed.failed":
            return {"status": "failed", "processed_features": 0}
        return {"status": "running", "processed_features": 0}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("boom")

    monkeypatch.setattr("gcjobs.app.db.record_import_event", fake_record_import_event)
    monkeypatch.setattr("gcjobs.app.db.get_import_run", fake_get_import_run)
    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={"file": ("source.geojson", "{}", "application/geo+json")},
        )

    assert response.status_code == 202
    assert response.json()["import_id"]
    assert recorded[0]["event"] == "import.accepted"
    assert recorded[1]["event"] == "import.completed.failed"
    assert recorded[1]["phase"] == "forwarding"


def test_import_start_records_gcimport_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    recorded: list[dict[str, str]] = []

    def fake_record_import_event(event, *, message_id=None):
        recorded.append(event)
        return {"id": event["import_id"]}

    def fake_get_import_run(_import_id):
        if not recorded:
            return None
        if recorded[-1]["event"] == "import.completed.failed":
            return {"status": "failed", "processed_features": 0}
        return {"status": "running", "processed_features": 0}

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            422,
            json={"detail": "uploaded file must contain valid UTF-8 JSON"},
        )

    monkeypatch.setattr("gcjobs.app.db.record_import_event", fake_record_import_event)
    monkeypatch.setattr("gcjobs.app.db.get_import_run", fake_get_import_run)
    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/imports?profile=fkb_bane",
            files={"file": ("source.geojson", "{", "application/json")},
        )

    assert response.status_code == 202
    assert recorded[0] == {
        "import_id": response.json()["import_id"],
        "event": "import.accepted",
        "phase": "accepted",
        "profile": "fkb_bane",
    }
    assert recorded[1]["event"] == "import.completed.failed"
    assert recorded[1]["phase"] == "forwarding"
    assert "422" in recorded[1]["reason"]
