from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import uuid4

import httpx2
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from gcjobs import config, db
from gcjobs.pubsub import ImportEventListener, RedisImportEventListener

# Reuse uvicorn's configured error logger so import-event logs reach the console
# in local/dev runs without additional logging setup.
LOGGER = logging.getLogger("uvicorn.error").getChild("gcjobs.import_events")

IMPORT_CLIENT_TIMEOUT = httpx2.Timeout(5.0, read=None)


def _lifespan(
    *,
    event_listener: ImportEventListener | None,
    import_client: httpx2.AsyncClient | None,
):
    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        listener = event_listener or RedisImportEventListener(config.redis_url())
        task = asyncio.create_task(_consume_import_events(listener))
        if import_client is not None:
            app_instance.state.import_client = import_client
            try:
                yield
            finally:
                await _cancel_task(task)
            return

        # Import execution is proxied synchronously through gcjobs and can take
        # longer than httpx's default read timeout on larger payloads.
        async with httpx2.AsyncClient(
            trust_env=False,
            timeout=IMPORT_CLIENT_TIMEOUT,
        ) as runtime_client:
            app_instance.state.import_client = runtime_client
            try:
                yield
            finally:
                await _cancel_task(task)

    return lifespan


async def _cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _register_routes(application: FastAPI) -> None:
    @application.get("/")
    def root() -> dict[str, str]:
        return {"service": config.SERVICE_NAME, "schema": config.DB_SCHEMA}

    @application.get("/healthz")
    def healthz() -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "ok",
            "service": config.SERVICE_NAME,
            "schema": config.DB_SCHEMA,
        }
        try:
            payload.update(db.health_status())
        except RuntimeError as err:
            payload["status"] = "misconfigured"
            payload["detail"] = str(err)
            return JSONResponse(payload, status_code=503)
        except Exception:
            payload["status"] = "unavailable"
            return JSONResponse(payload, status_code=503)
        return payload

    @application.post("/imports")
    async def create_import(
        background_tasks: BackgroundTasks,
        request: Request,
        profile_name: str = Query(alias="profile"),
    ) -> JSONResponse:
        import_id = str(uuid4())
        payload = await request.body()
        content_type = request.headers.get("content-type", "application/octet-stream")

        db.record_import_event(
            {
                "import_id": import_id,
                "event": "import.accepted",
                "phase": "accepted",
                "profile": profile_name,
            }
        )

        background_tasks.add_task(
            _proxy_import,
            application.state.import_client,
            import_id,
            profile_name,
            content_type,
            payload,
        )

        return JSONResponse(
            {
                "import_id": import_id,
                "status": "accepted",
            },
            status_code=202,
        )

    @application.get("/imports/current")
    def current_imports() -> dict[str, list[dict[str, Any]]]:
        return {"imports": db.list_import_runs(active_only=True)}

    @application.get("/imports/history")
    def import_history() -> dict[str, list[dict[str, Any]]]:
        return {"imports": db.list_import_runs(active_only=False)}

    @application.get("/imports/{import_id}")
    def import_run(import_id: str) -> dict[str, Any]:
        row = db.get_import_run(import_id)
        if row is None:
            raise HTTPException(status_code=404, detail="import run not found")
        return row

    @application.get("/imports/{import_id}/events")
    def import_events_history(import_id: str) -> dict[str, list[dict[str, Any]]]:
        if db.get_import_run(import_id) is None:
            raise HTTPException(status_code=404, detail="import run not found")
        return {"events": db.get_import_events(import_id)}


def create_app(
    *,
    event_listener: ImportEventListener | None = None,
    import_client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    application = FastAPI(
        title="gcjobs",
        version="0.1.0",
        lifespan=_lifespan(
            event_listener=event_listener,
            import_client=import_client,
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_routes(application)

    return application


async def _proxy_import(
    import_client: httpx2.AsyncClient,
    import_id: str,
    profile_name: str,
    content_type: str,
    payload: bytes,
) -> None:
    try:
        response = await import_client.post(
            f"{config.gcimport_api_url()}/imports",
            params={"profile": profile_name},
            headers={
                "X-Import-Id": import_id,
                "Content-Type": content_type,
            },
            content=payload,
        )
        response.raise_for_status()
    except httpx2.HTTPError as err:
        _record_proxy_terminal_event(
            import_id,
            {
                "import_id": import_id,
                "event": "import.completed.failed",
                "phase": "forwarding",
                "profile": profile_name,
                "reason": f"gcjobs could not reach gcimport: {err}",
            },
        )
        LOGGER.exception("Import proxy failed", extra={"import_id": import_id})
        return


def _record_proxy_terminal_event(import_id: str, event: dict[str, Any]) -> None:
    if _run_is_terminal(db.get_import_run(import_id)):
        return
    db.record_import_event(event)


def _run_is_terminal(run: dict[str, Any] | None) -> bool:
    return run is not None and run.get("status") in {"completed", "failed"}


async def _consume_import_events(listener: ImportEventListener) -> None:
    try:
        async for message in listener.messages():
            db.record_import_event(message.event, message_id=message.message_id)
            await message.ack()
            LOGGER.info("import event %s", _event_for_log(message.event))
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("Import event listener stopped")


def _event_for_log(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(event)
    feature_ids = sanitized.pop("feature_ids", None)
    if isinstance(feature_ids, list):
        sanitized["feature_id_count"] = len(feature_ids)
    return sanitized


app = create_app()
