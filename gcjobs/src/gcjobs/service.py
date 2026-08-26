from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any
from uuid import uuid4

import httpx2
from fastapi import FastAPI, HTTPException, Request

from gcjobs import config, storage
from gcjobs.pubsub import ImportEventListener, RedisImportEventListener

# Reuse uvicorn's configured error logger so import-event logs reach the console
# in local/dev runs without additional logging setup.
LOGGER = logging.getLogger("uvicorn.error").getChild("gcjobs.import_events")

IMPORT_CLIENT_TIMEOUT = httpx2.Timeout(5.0, read=None)


def build_lifespan(
    *,
    event_listener: ImportEventListener | None,
    import_client: httpx2.AsyncClient | None,
):
    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        listener = event_listener or RedisImportEventListener(config.redis_url())
        app_instance.state.proxy_tasks.clear()
        task = asyncio.create_task(consume_import_events(listener))
        try:
            async with _import_client_context(import_client) as runtime_client:
                app_instance.state.import_client = runtime_client
                yield
        finally:
            await _cancel_proxy_tasks(app_instance)
            await _cancel_task(task)

    return lifespan


async def queue_import_request(
    request: Request,
    import_client: httpx2.AsyncClient,
    dataset_name: str,
) -> str:
    payload = await _read_bounded_request_body(request, config.max_upload_bytes())
    import_id = str(uuid4())
    content_type = request.headers.get("content-type", "application/octet-stream")

    storage.record_accepted_import(import_id, dataset_name)

    proxy_task = asyncio.create_task(
        proxy_import(
            import_client,
            import_id,
            dataset_name,
            content_type,
            payload,
        )
    )
    root_app = getattr(request.app.state, "root_app", request.app)
    proxy_tasks = root_app.state.proxy_tasks
    proxy_tasks.add(proxy_task)
    proxy_task.add_done_callback(proxy_tasks.discard)
    return import_id


async def proxy_import(
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
        storage.record_terminal_event_if_running(
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


async def consume_import_events(listener: ImportEventListener) -> None:
    try:
        async for message in listener.messages():
            storage.record_import_event(message.event, message_id=message.message_id)
            await message.ack()
            LOGGER.info("import event %s", _event_for_log(message.event))
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception("Import event listener stopped")


def _declared_content_length(headers: Any) -> int | None:
    raw_value = headers.get("content-length")
    if raw_value is None:
        return None

    try:
        value = int(raw_value)
    except ValueError:
        return None

    return value if value >= 0 else None


async def _read_bounded_request_body(request: Request, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0

    for declared_length in (_declared_content_length(request.headers),):
        if declared_length is not None and declared_length > max_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")

    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")
        chunks.append(chunk)

    return b"".join(chunks)


@asynccontextmanager
async def _import_client_context(
    import_client: httpx2.AsyncClient | None,
) -> AsyncIterator[httpx2.AsyncClient]:
    if import_client is not None:
        yield import_client
        return

    # Import execution is proxied synchronously through gcjobs and can take
    # longer than httpx's default read timeout on larger payloads.
    async with httpx2.AsyncClient(
        trust_env=False,
        timeout=IMPORT_CLIENT_TIMEOUT,
    ) as runtime_client:
        yield runtime_client


async def _cancel_proxy_tasks(app_instance: FastAPI) -> None:
    for proxy_task in tuple(app_instance.state.proxy_tasks):
        await _cancel_task(proxy_task)


async def _cancel_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def _event_for_log(event: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(event)
    feature_ids = sanitized.pop("feature_ids", None)
    if isinstance(feature_ids, list):
        sanitized["feature_id_count"] = len(feature_ids)
    return sanitized
