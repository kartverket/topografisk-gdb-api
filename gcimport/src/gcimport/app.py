"""FastAPI composition root for gcimport."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import Annotated, Any

import httpx
import orjson
from fastapi import FastAPI, File, HTTPException, UploadFile, status

from gcimport.config import Settings
from gcimport.geojson_to_jsonfg import ConversionError, convert_document
from gcimport.importer import (
    DocumentValidationError,
    UpstreamImportError,
    import_features,
    prepare_document,
)
from gcimport.profiles import BANE_PROFILE, ImportProfile

READ_CHUNK_BYTES = 64 * 1024
CLASSIC_GEOJSON_SUFFIX = ".geojson"


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    profile: ImportProfile = BANE_PROFILE,
) -> FastAPI:
    """Create an app with optionally injected configuration and HTTP client."""

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or Settings.from_env(profile.default_api_url)
        app_instance.state.settings = runtime_settings
        if client is not None:
            app_instance.state.http_client = client
            yield
            return

        async with httpx.AsyncClient(
            timeout=runtime_settings.request_timeout_seconds
        ) as runtime_client:
            app_instance.state.http_client = runtime_client
            yield

    application = FastAPI(
        title="gcimport",
        description=(
            f"JSON-FG / classic GeoJSON (.geojson) importer using the "
            f"{profile.title} profile"
        ),
        lifespan=lifespan,
    )

    @application.post("/imports")
    async def create_import(file: Annotated[UploadFile, File()]) -> dict:
        runtime_settings: Settings = application.state.settings
        body = await _read_bounded(file, runtime_settings.max_upload_bytes)
        try:
            document = orjson.loads(body)
        except orjson.JSONDecodeError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="uploaded file must contain valid UTF-8 JSON",
            ) from err

        try:
            document = _normalize_upload(document, file.filename)
            features = prepare_document(document, profile)
        except ConversionError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "message": "invalid classic GeoJSON document",
                    "errors": [str(err)],
                },
            ) from err
        except DocumentValidationError as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"message": "invalid JSON-FG document", "errors": err.errors},
            ) from err

        try:
            return await import_features(
                features,
                client=application.state.http_client,
                api_url=runtime_settings.api_url,
            )
        except UpstreamImportError as err:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"{profile.title} API upsert failed",
                    "collection": err.collection,
                    "id": err.feature_id,
                    "reason": err.reason,
                },
            ) from err

    return application


def _is_classic_geojson_filename(filename: str | None) -> bool:
    if not filename:
        return False
    return PurePosixPath(filename).suffix.casefold() == CLASSIC_GEOJSON_SUFFIX


def _normalize_upload(document: Any, filename: str | None) -> Any:
    """Convert classic GeoJSON uploads; leave JSON-FG uploads unchanged."""
    if not _is_classic_geojson_filename(filename):
        return document
    return convert_document(document)


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
