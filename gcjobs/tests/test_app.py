import json as jsonlib
import logging
from datetime import UTC, datetime

import httpx2
import pytest
from fastapi.testclient import TestClient

from gcjobs.app import create_app
from gcjobs.pubsub import StubImportEventListener


def _dataset_api(dataset_name: str) -> str:
    return f"/datasets/{dataset_name}/ogc_api"


def test_root_reports_service_identity() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"service": "gcjobs", "schema": "gc_jobs"}


def test_create_app_rejects_empty_descriptions_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("gcjobs.app.config.descriptions_dir", lambda: tmp_path)

    with pytest.raises(RuntimeError, match="no dataset descriptions found"):
        create_app(event_listener=StubImportEventListener([]))


def test_imports_preflight_allows_any_origin() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.options(
        f"{_dataset_api('fkb_bane')}/processes/import/execution",
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
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
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
    assert response.json()["processID"] == "import"
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


def test_process_execution_proxies_multiple_files_to_gcimport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr("gcjobs.app.config.max_upload_bytes", lambda: 1024 * 1024)
    requests: list[httpx2.Request] = []

    monkeypatch.setattr(
        "gcjobs.app.db.record_import_event",
        lambda event, *, message_id=None: {"id": event["import_id"]},
    )

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        assert b'filename="source-1.geojson"' in request.content
        assert b'filename="source-2.geojson"' in request.content
        return httpx2.Response(200, json={"total": 2, "features": []})

    proxy_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    app = create_app(
        event_listener=StubImportEventListener([]),
        import_client=proxy_client,
    )

    with TestClient(app) as client:
        response = client.post(
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
            files=[
                (
                    "file",
                    (
                        "source-1.geojson",
                        jsonlib.dumps({"type": "FeatureCollection", "features": []}),
                        "application/geo+json",
                    ),
                ),
                (
                    "file",
                    (
                        "source-2.geojson",
                        jsonlib.dumps({"type": "FeatureCollection", "features": []}),
                        "application/geo+json",
                    ),
                ),
            ],
        )

    assert response.status_code == 201
    assert len(requests) == 1
    assert requests[0].url == "http://gcimport:8000/imports?profile=fkb_bane"


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
            f"{_dataset_api('fkb_bane')}/processes/not_a_process/execution",
            content=b"{}",
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "processID must be one of: import"}
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
            f"{_dataset_api('bygning')}/processes/import/execution",
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
            f"{_dataset_api('bygning')}/processes/import/execution",
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
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
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
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
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


def test_datasets_endpoint_lists_shared_descriptions() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/datasets")

    assert response.status_code == 200
    dataset_ids = {dataset["id"] for dataset in response.json()["datasets"]}
    assert {"bygning", "cadastre", "fkb_bane"} <= dataset_ids


def test_processes_endpoint_is_dataset_scoped() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(f"{_dataset_api('fkb_bane')}/processes")

    assert response.status_code == 200
    assert [process["id"] for process in response.json()["processes"]] == ["import"]


def test_non_import_dataset_exposes_empty_process_list() -> None:
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(f"{_dataset_api('cadastre')}/processes")

    assert response.status_code == 200
    assert response.json()["processes"] == []


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
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
            files={"file": ("source.geojson", "{}", "application/geo+json")},
        )

    assert response.status_code == 201
    assert response.headers["location"].endswith(
        f"{_dataset_api('fkb_bane')}/jobs/{response.json()['jobID']}"
    )
    assert response.json()["status"] == "accepted"
    assert response.json()["processID"] == "import"


def test_process_execution_uses_configured_api_base_url_for_job_urls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.gcimport_api_url", lambda: "http://gcimport:8000"
    )
    monkeypatch.setattr(
        "gcjobs.app.config.api_base_url", lambda: "https://gcapi.example.no/edge"
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
            f"{_dataset_api('fkb_bane')}/processes/import/execution",
            files={"file": ("source.geojson", "{}", "application/geo+json")},
        )

    expected_job_url = f"https://gcapi.example.no/edge{_dataset_api('fkb_bane')}/jobs/{response.json()['jobID']}"
    assert response.status_code == 201
    assert response.headers["location"] == expected_job_url
    assert response.json()["links"][0]["href"] == expected_job_url
    assert response.json()["links"][1]["href"] == (
        f"https://gcapi.example.no/edge{_dataset_api('fkb_bane')}/jobs"
    )


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

    response = client.get(
        f"{_dataset_api('fkb_bane')}/jobs?type=process&processID=import"
    )

    assert response.status_code == 200
    assert response.json()["jobs"] == [
        {
            "type": "process",
            "jobID": "job-1",
            "processID": "import",
            "status": "successful",
            "message": "Import completed",
            "links": [
                {
                    "href": f"http://localhost:8000{_dataset_api('fkb_bane')}/jobs/job-1",
                    "rel": "self",
                    "type": "application/json",
                    "title": "This document",
                },
                {
                    "href": f"http://localhost:8000{_dataset_api('fkb_bane')}/jobs",
                    "rel": "up",
                    "type": "application/json",
                    "title": "Job list",
                },
                {
                    "href": f"http://localhost:8000{_dataset_api('fkb_bane')}/jobs/job-1/results",
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


def test_datasets_endpoint_uses_configured_api_base_url_in_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.api_base_url", lambda: "https://gcapi.example.no/edge"
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get("/datasets")

    assert response.status_code == 200
    assert response.json()["datasets"][0]["links"][0]["href"].startswith(
        "https://gcapi.example.no/edge/datasets/"
    )


def test_jobs_endpoint_uses_configured_api_base_url_for_self_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.config.api_base_url", lambda: "https://gcapi.example.no/edge"
    )
    monkeypatch.setattr(
        "gcjobs.app.db.list_import_runs",
        lambda *, active_only, limit=50: [],
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(
        f"{_dataset_api('fkb_bane')}/jobs?type=process&processID=import"
    )

    assert response.status_code == 200
    assert response.json()["links"][0]["href"] == (
        "https://gcapi.example.no/edge/datasets/fkb_bane/ogc_api/jobs?type=process&processID=import"
    )


def test_job_results_returns_summary_for_successful_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_run",
        lambda _job_id: {
            "id": "job-1",
            "profile": "fkb_bane",
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
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_events",
        lambda _job_id, limit=500: [
            {
                "payload": {
                    "filenames": ["source-1.geojson", "source-2.geojson"],
                }
            }
        ],
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(f"{_dataset_api('fkb_bane')}/jobs/job-1/results")

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
            "filenames": ["source-1.geojson", "source-2.geojson"],
        }
    }


def test_job_endpoint_returns_uploaded_filenames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_run",
        lambda _job_id: {
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
    )
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_events",
        lambda _job_id, limit=500: [
            {
                "payload": {
                    "filenames": ["source-1.geojson", "source-2.geojson"],
                }
            }
        ],
    )
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(f"{_dataset_api('fkb_bane')}/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["filenames"] == ["source-1.geojson", "source-2.geojson"]


def test_job_endpoint_serializes_datetime_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "gcjobs.app.db.get_import_run",
        lambda _job_id: {
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
            "started_at": datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
            "completed_at": datetime(2026, 8, 24, 10, 1, tzinfo=UTC),
            "last_event_at": datetime(2026, 8, 24, 10, 1, tzinfo=UTC),
            "last_error": None,
        },
    )
    monkeypatch.setattr("gcjobs.app.db.get_import_events", lambda _job_id, limit=5: [])
    client = TestClient(create_app(event_listener=StubImportEventListener([])))

    response = client.get(f"{_dataset_api('fkb_bane')}/jobs/job-1")

    assert response.status_code == 200
    assert response.json()["created"] == "2026-08-24T10:00:00Z"
    assert response.json()["started"] == "2026-08-24T10:00:00Z"
    assert response.json()["finished"] == "2026-08-24T10:01:00Z"
    assert response.json()["updated"] == "2026-08-24T10:01:00Z"
