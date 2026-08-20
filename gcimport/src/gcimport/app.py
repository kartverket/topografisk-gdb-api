"""FastAPI composition root for gcimport."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ImportRequestContext:
    application: FastAPI
    runtime_settings: Settings
    publisher: ImportEventPublisher
    request_profile: ImportProfile
    base_event: dict[str, Any]


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
        runtime_publisher = event_publisher or RedisImportEventPublisher(
            runtime_settings.redis_url
        )
        app_instance.state.settings = runtime_settings
        app_instance.state.event_publisher = runtime_publisher
        if client is not None:
            app_instance.state.http_client = client
            try:
                yield
            finally:
                await _close_event_publisher(runtime_publisher)
            return

        async with httpx2.AsyncClient(
            timeout=runtime_settings.request_timeout_seconds
        ) as runtime_client:
            app_instance.state.http_client = runtime_client
            try:
                yield
            finally:
                await _close_event_publisher(runtime_publisher)

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
        return await _handle_import_request(
            application=application,
            file=file,
            profile_name=profile_name,
            requested_import_id=requested_import_id,
        )

    return application


async def _handle_import_request(
    *,
    application: FastAPI,
    file: UploadFile,
    profile_name: str,
    requested_import_id: str | None,
) -> dict[str, Any]:
    runtime_settings: Settings = application.state.settings
    publisher: ImportEventPublisher = application.state.event_publisher
    request_profile = _request_profile(profile_name)
    body = await _read_bounded(file, runtime_settings.max_upload_bytes)
    import_id = _request_import_id(requested_import_id)
    context = ImportRequestContext(
        application=application,
        runtime_settings=runtime_settings,
        publisher=publisher,
        request_profile=request_profile,
        base_event=_base_event(
            request_profile=request_profile,
            import_id=import_id,
            filename=file.filename,
        ),
    )

    await _publish_import_update(
        publisher,
        context.base_event,
        event_name="import.started",
        phase="parsing",
    )
    document = await _load_import_document(body, publisher, context.base_event)
    features = await _prepare_import_features(
        document=document,
        filename=file.filename,
        request_profile=request_profile,
        publisher=publisher,
        base_event=context.base_event,
    )
    total_features = len(features)
    await _publish_import_update(
        publisher,
        context.base_event,
        event_name="import.parsed",
        phase="importing",
        total_features=total_features,
    )
    result = await _run_import(context, features, total_features)
    await _publish_import_update(
        publisher,
        context.base_event,
        event_name="import.completed.succeeded",
        phase="completed",
        total_features=total_features,
        imported_features=result["total"],
    )
    return result


def _request_import_id(requested_import_id: str | None) -> str:
    import_id = requested_import_id.strip() if requested_import_id else ""
    if import_id:
        return import_id
    return str(uuid4())


def _base_event(
    *,
    request_profile: ImportProfile,
    import_id: str,
    filename: str | None,
) -> dict[str, Any]:
    return {
        "import_id": import_id,
        "profile": request_profile.name,
        "dataset_api_path": request_profile.dataset_api_path,
        "filename": filename,
    }


def _import_event(
    base_event: dict[str, Any],
    *,
    event_name: str,
    phase: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        **base_event,
        "event": event_name,
        "phase": phase,
        "timestamp": _timestamp(),
        **extra,
    }


async def _publish_import_update(
    publisher: ImportEventPublisher,
    base_event: dict[str, Any],
    *,
    event_name: str,
    phase: str,
    **extra: Any,
) -> None:
    await _publish_event(
        publisher,
        _import_event(base_event, event_name=event_name, phase=phase, **extra),
    )


async def _load_import_document(
    body: bytes,
    publisher: ImportEventPublisher,
    base_event: dict[str, Any],
) -> Any:
    try:
        return orjson.loads(body)
    except orjson.JSONDecodeError as err:
        await _publish_import_update(
            publisher,
            base_event,
            event_name="import.completed.failed",
            phase="parsing",
            reason="uploaded file must contain valid UTF-8 JSON",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="uploaded file must contain valid UTF-8 JSON",
        ) from err


async def _prepare_import_features(
    *,
    document: Any,
    filename: str | None,
    request_profile: ImportProfile,
    publisher: ImportEventPublisher,
    base_event: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        normalized_document = _normalize_upload(document, filename, request_profile)
        return prepare_document(normalized_document, request_profile)
    except ConversionError as err:
        await _publish_import_update(
            publisher,
            base_event,
            event_name="import.completed.failed",
            phase="parsing",
            reason=str(err),
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": "invalid classic GeoJSON document",
                "errors": [str(err)],
            },
        ) from err
    except DocumentValidationError as err:
        await _publish_import_update(
            publisher,
            base_event,
            event_name="import.completed.failed",
            phase="parsing",
            errors=err.errors,
            reason="invalid JSON-FG document",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"message": "invalid JSON-FG document", "errors": err.errors},
        ) from err


def _batch_event_publisher(
    publisher: ImportEventPublisher,
    base_event: dict[str, Any],
    total_features: int,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    async def publish_batch_event(batch_event: dict[str, Any]) -> None:
        suffix = batch_event["status"]
        await _publish_import_update(
            publisher,
            base_event,
            event_name=f"import.batch.{suffix}",
            phase="importing",
            total_features=total_features,
            **batch_event,
        )

    return publish_batch_event


async def _run_import(
    context: ImportRequestContext,
    features: list[dict[str, Any]],
    total_features: int,
) -> dict[str, Any]:
    try:
        return await import_features(
            features,
            client=context.application.state.http_client,
            api_url=_dataset_api_url(
                context.runtime_settings.geocomponents_api_url,
                context.request_profile,
            ),
            upsert_batch_size=context.runtime_settings.upsert_batch_size,
            on_batch=_batch_event_publisher(
                context.publisher,
                context.base_event,
                total_features,
            ),
        )
    except UpstreamImportError as err:
        await _publish_import_update(
            context.publisher,
            context.base_event,
            event_name="import.completed.failed",
            phase="importing",
            total_features=total_features,
            collection=err.collection,
            feature_id=err.feature_id,
            reason=err.reason,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "message": f"{context.request_profile.title} API upsert failed",
                "collection": err.collection,
                "id": err.feature_id,
                "reason": err.reason,
            },
        ) from err


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


async def _close_event_publisher(publisher: ImportEventPublisher) -> None:
    close = getattr(publisher, "aclose", None)
    if close is None:
        return
    await close()


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
