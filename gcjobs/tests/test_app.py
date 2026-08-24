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
        "/processes/import-fkb-bane/execution",
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


def test_process_execution_proxies_to_gcimport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
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
            "/processes/import-fkb-bane/execution",
            files={
                "file": (
                    "source.geojson",
                    jsonlib.dumps({"type": "FeatureCollection", "features": []}),
                    "application/geo+json",
                )
            },
        )

    assert response.status_code == 201
    assert response.json()["jobID"]
    assert response.json()["status"] == "accepted"
    assert response.json()["processID"] == "import-fkb-bane"
    assert requests[0].url == "http://gcimport:8000/imports?profile=fkb_bane"
    assert requests[0].headers["x-import-id"] == response.json()["jobID"]
    assert recorded == [
        {
            "import_id": response.json()["jobID"],
            "event": "import.accepted",
            "phase": "accepted",
            "profile": "fkb_bane",
        }
    ]


def test_process_execution_rejects_unknown_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
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
            "/processes/not_a_profile/execution",
            content=b"{}",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "processID must be one of: import-bygning, import-fkb-bane"
    }
    assert recorded == []
    assert requests == []


def test_process_execution_rejects_non_multipart_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json={"total": 1, "features": []})

    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/processes/import-bygning/execution",
            content=b"{}",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 415
    assert response.json() == {
        "detail": "Import processes require multipart/form-data uploads"
    }
    assert requests == []


def test_process_execution_rejects_oversized_request_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 4)
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
            "/processes/import-bygning/execution",
            files={"file": ("source.geojson", b"12345", "application/geo+json")},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "upload exceeds size limit"}
    assert recorded == []
    assert requests == []


def test_declared_content_length_helper_rejects_oversized_value() -> None:
    from gcjobs.app import _declared_content_length

    assert _declared_content_length({"content-length": "6"}) == 6
    assert _declared_content_length({"content-length": "abc"}) is None
    assert _declared_content_length({"content-length": "-1"}) is None


def test_process_execution_records_forwarding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
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
            "/processes/import-fkb-bane/execution",
            files={"file": ("source.geojson", "{}", "application/geo+json")},
        )

    assert response.status_code == 201
    assert response.json()["jobID"]
    assert recorded[0]["event"] == "import.accepted"
    assert recorded[1]["event"] == "import.completed.failed"
    assert recorded[1]["phase"] == "forwarding"


def test_process_execution_records_gcimport_http_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
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
            "/processes/import-fkb-bane/execution",
            files={"file": ("source.geojson", "{", "application/json")},
        )

    assert response.status_code == 201
    assert recorded[0] == {
        "import_id": response.json()["jobID"],
        "event": "import.accepted",
        "phase": "accepted",
        "profile": "fkb_bane",
    }
    assert recorded[1]["event"] == "import.completed.failed"
    assert recorded[1]["phase"] == "forwarding"
    assert "422" in recorded[1]["reason"]


def test_processes_endpoint_lists_import_processes() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/processes")

    assert response.status_code == 200
    body = response.json()
    assert [process["id"] for process in body["processes"]] == [
        "import-bygning",
        "import-fkb-bane",
    ]


def test_process_execution_returns_created_job_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
    monkeypatch.setattr(
        "gcjobs.app.db.record_import_event",
        lambda event, *, message_id=None: {"id": event["import_id"]},
    )

    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"total": 1, "features": []})

    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            "/processes/import-fkb-bane/execution",
            files={"file": ("source.geojson", "{}", "application/geo+json")},
        )

    assert response.status_code == 201
    assert response.headers["location"].endswith(f"/jobs/{response.json()['jobID']}")
    assert response.json()["status"] == "accepted"
    assert response.json()["processID"] == "import-fkb-bane"


def test_jobs_endpoint_returns_filtered_mapped_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.list_import_runs",
        lambda *, active_only, limit=50: [
            {
                "id": "job-1",
                "profile": "fkb_bane",
                "status": "completed",
                "phase": "completed",
                "total_features": 2,
                "processed_features": 2,
                "succeeded_features": 2,
                "failed_features": 0,
                "processed_batches": 1,
                "succeeded_batches": 1,
                "failed_batches": 0,
                "started_at": "2026-08-24T10:00:00Z",
                "completed_at": "2026-08-24T10:01:00Z",
                "last_event_at": "2026-08-24T10:01:00Z",
                "last_error": None,
            },
            {
                "id": "job-2",
                "profile": "bygning",
                "status": "running",
                "phase": "parsing",
                "total_features": 4,
                "processed_features": 1,
                "succeeded_features": 1,
                "failed_features": 0,
                "processed_batches": 1,
                "succeeded_batches": 1,
                "failed_batches": 0,
                "started_at": "2026-08-24T10:02:00Z",
                "completed_at": None,
                "last_event_at": "2026-08-24T10:03:00Z",
                "last_error": None,
            },
        ],
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/jobs?type=process&processID=import-fkb-bane")

    assert response.status_code == 200
    assert response.json()["jobs"] == [
        {
            "type": "process",
            "jobID": "job-1",
            "processID": "import-fkb-bane",
            "status": "successful",
            "message": "Import completed",
            "links": [
                {
                    "href": "http://testserver/jobs/job-1",
                    "rel": "self",
                    "type": "application/json",
                    "title": "This document",
                },
                {
                    "href": "http://testserver/jobs",
                    "rel": "up",
                    "type": "application/json",
                    "title": "Job list",
                },
                {
                    "href": "http://testserver/jobs/job-1/results",
                    "rel": "http://www.opengis.net/def/rel/ogc/1.0/results",
                    "type": "application/json",
                    "title": "Job results",
                },
            ],
            "updated": "2026-08-24T10:01:00Z",
            "phase": "completed",
            "totalFeatures": 2,
            "processedFeatures": 2,
            "succeededFeatures": 2,
            "failedFeatures": 0,
            "processedBatches": 1,
            "succeededBatches": 1,
            "failedBatches": 0,
            "progress": 100,
            "created": "2026-08-24T10:00:00Z",
            "started": "2026-08-24T10:00:00Z",
            "finished": "2026-08-24T10:01:00Z",
        }
    ]


def test_job_results_returns_summary_for_successful_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_run",
        lambda _job_id: {
            "id": "job-1",
            "status": "completed",
            "phase": "completed",
            "processed_features": 2,
            "succeeded_features": 2,
            "failed_features": 0,
            "processed_batches": 1,
            "succeeded_batches": 1,
            "failed_batches": 0,
            "total_features": 2,
            "completed_at": "2026-08-24T10:01:00Z",
        },
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/jobs/job-1/results")

    assert response.status_code == 200
    assert response.json() == {
        "summary": {
            "jobID": "job-1",
            "processedFeatures": 2,
            "succeededFeatures": 2,
            "failedFeatures": 0,
            "processedBatches": 1,
            "succeededBatches": 1,
            "failedBatches": 0,
            "totalFeatures": 2,
            "completed": "2026-08-24T10:01:00Z",
        }
    }
