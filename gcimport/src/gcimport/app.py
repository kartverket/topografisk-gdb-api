"""FastAPI composition root for gcimport."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Any
from uuid import uuid4

import httpx2
import orjson
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from gcimport.config import Settings
from gcimport.geojson_to_jsonfg import ConversionError, convert_document
from gcimport.importer import (
    DocumentValidationError,
    UpstreamImportError,
    import_features,
    prepare_document,
)
from gcimport.profiles import BUILTIN_PROFILES, ImportProfile, get_profile
from gcimport.pubsub import ImportEventPublisher, RedisImportEventPublisher

READ_CHUNK_BYTES = 64 * 1024
CLASSIC_GEOJSON_SUFFIX = ".geojson"
LOGGER = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx2.AsyncClient | None = None,
    event_publisher: ImportEventPublisher | None = None,
) -> FastAPI:
    """Create an app with optionally injected configuration and HTTP client."""

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or Settings.from_env()
        app_instance.state.settings = runtime_settings
        if client is not None:
            app_instance.state.event_publisher = (
                event_publisher or RedisImportEventPublisher(runtime_settings.redis_url)
            )
            app_instance.state.http_client = client
            yield
            return

        async with httpx2.AsyncClient(
            timeout=runtime_settings.request_timeout_seconds
        ) as runtime_client:
            app_instance.state.event_publisher = (
                event_publisher or RedisImportEventPublisher(runtime_settings.redis_url)
            )
            app_instance.state.http_client = runtime_client
            yield

    application = FastAPI(
        title="gcimport",
        description=(
            "JSON-FG / classic GeoJSON (.geojson) importer using an explicitly "
            "selected built-in profile"
        ),
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.post("/imports")
    async def create_import(
        file: Annotated[UploadFile, File()],
        profile_name: Annotated[str, Query(alias="profile")],
        requested_import_id: Annotated[
            str | None,
            Header(alias="X-Import-Id"),
        ] = None,
    ) -> dict:
        runtime_settings: Settings = application.state.settings
        publisher: ImportEventPublisher = application.state.event_publisher
        request_profile = _request_profile(profile_name)
        body = await _read_bounded(file, runtime_settings.max_upload_bytes)
        import_id = requested_import_id.strip() if requested_import_id else str(uuid4())
        if not import_id:
            import_id = str(uuid4())
        base_event = {
            "import_id": import_id,
            "profile": request_profile.name,
            "dataset_api_path": request_profile.dataset_api_path,
            "filename": file.filename,
        }

        await _publish_event(
            publisher,
            {
                **base_event,
                "event": "import.started",
                "phase": "parsing",
                "timestamp": _timestamp(),
            },
        )
        try:
            document = orjson.loads(body)
        except orjson.JSONDecodeError as err:
            await _publish_event(
                publisher,
                {
                    **base_event,
                    "event": "import.completed.failed",
                    "phase": "parsing",
                    "timestamp": _timestamp(),
                    "reason": "uploaded file must contain valid UTF-8 JSON",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="uploaded file must contain valid UTF-8 JSON",
            ) from err

        try:
            document = _normalize_upload(document, file.filename, request_profile)
            features = prepare_document(document, request_profile)
        except ConversionError as err:
            await _publish_event(
                publisher,
                {
                    **base_event,
                    "event": "import.completed.failed",
                    "phase": "parsing",
                    "timestamp": _timestamp(),
                    "reason": str(err),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "invalid classic GeoJSON document",
                    "errors": [str(err)],
                },
            ) from err
        except DocumentValidationError as err:
            await _publish_event(
                publisher,
                {
                    **base_event,
                    "event": "import.completed.failed",
                    "phase": "parsing",
                    "timestamp": _timestamp(),
                    "errors": err.errors,
                    "reason": "invalid JSON-FG document",
                },
            )
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"message": "invalid JSON-FG document", "errors": err.errors},
            ) from err

        await _publish_event(
            publisher,
            {
                **base_event,
                "event": "import.parsed",
                "phase": "importing",
                "timestamp": _timestamp(),
                "total_features": len(features),
            },
        )

        async def publish_batch_event(batch_event: dict[str, Any]) -> None:
            suffix = batch_event.pop("status")
            await _publish_event(
                publisher,
                {
                    **base_event,
                    **batch_event,
                    "event": f"import.batch.{suffix}",
                    "phase": "importing",
                    "timestamp": _timestamp(),
                    "total_features": len(features),
                },
            )

        try:
            result = await import_features(
                features,
                client=application.state.http_client,
                api_url=_dataset_api_url(
                    runtime_settings.geocomponents_api_url,
                    request_profile,
                ),
                upsert_batch_size=runtime_settings.upsert_batch_size,
                on_batch=publish_batch_event,
            )
        except UpstreamImportError as err:
            await _publish_event(
                publisher,
                {
                    **base_event,
                    "event": "import.completed.failed",
                    "phase": "importing",
                    "timestamp": _timestamp(),
                    "total_features": len(features),
                    "collection": err.collection,
                    "feature_id": err.feature_id,
                    "reason": err.reason,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"{request_profile.title} API upsert failed",
                    "collection": err.collection,
                    "id": err.feature_id,
                    "reason": err.reason,
                },
            ) from err

        await _publish_event(
            publisher,
            {
                **base_event,
                "event": "import.completed.succeeded",
                "phase": "completed",
                "timestamp": _timestamp(),
                "total_features": len(features),
                "imported_features": result["total"],
            },
        )
        return result

    return application


async def _publish_event(
    publisher: ImportEventPublisher,
    event: dict[str, Any],
) -> None:
    try:
        await publisher.publish(event)
    except Exception:
        LOGGER.warning(
            "Failed to publish import event %s", event.get("event"), exc_info=True
        )


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _is_classic_geojson_filename(filename: str | None) -> bool:
    if not filename:
        return False
    return PurePosixPath(filename).suffix.casefold() == CLASSIC_GEOJSON_SUFFIX


def _normalize_upload(
    document: Any,
    filename: str | None,
    profile: ImportProfile,
) -> Any:
    """Convert classic GeoJSON uploads; leave JSON-FG uploads unchanged."""
    if not _is_classic_geojson_filename(filename):
        return document
    return convert_document(document, profile=profile)


def _request_profile(
    profile_name: str,
) -> ImportProfile:
    try:
        return get_profile(profile_name)
    except ValueError as err:
        supported = ", ".join(sorted(BUILTIN_PROFILES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"profile must be one of: {supported}",
        ) from err


def _dataset_api_url(root_api_url: str, profile: ImportProfile) -> str:
    return f"{root_api_url.rstrip('/')}/{profile.dataset_api_path.strip('/')}"


async def _read_bounded(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        while chunk := await file.read(READ_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"uploaded file exceeds {max_bytes} bytes",
                )
            chunks.append(chunk)
    finally:
        await file.close()
    return b"".join(chunks)


app = create_app()
