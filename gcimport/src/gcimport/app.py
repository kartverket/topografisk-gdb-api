"""FastAPI composition root for gcimport."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import orjson
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status

from gcimport.config import Settings
from gcimport.geojson_to_jsonfg import ConversionError, convert_document
from gcimport.importer import (
    DocumentValidationError,
    UpstreamImportError,
    import_features,
    prepare_document,
)
from gcimport.profiles import BANE_PROFILE, BUILTIN_PROFILES, ImportProfile, get_profile

READ_CHUNK_BYTES = 64 * 1024
CLASSIC_GEOJSON_SUFFIX = ".geojson"
PROFILE_ENV_NAME = "GCIMPORT_PROFILE"


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    profile: ImportProfile | None = None,
) -> FastAPI:
    """Create an app with optionally injected configuration and HTTP client."""
    resolved_profile = profile or _profile_from_env()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        runtime_settings = settings or Settings.from_env(
            resolved_profile.default_api_url
        )
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
            f"{resolved_profile.title} profile"
        ),
        lifespan=lifespan,
    )

    @application.post("/imports")
    async def create_import(
        file: Annotated[UploadFile, File()],
        profile_name: Annotated[str | None, Query(alias="profile")] = None,
    ) -> dict:
        runtime_settings: Settings = application.state.settings
        request_profile = _request_profile(profile_name, resolved_profile)
        body = await _read_bounded(file, runtime_settings.max_upload_bytes)
        try:
            document = orjson.loads(body)
        except orjson.JSONDecodeError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="uploaded file must contain valid UTF-8 JSON",
            ) from err

        try:
            document = _normalize_upload(document, file.filename, request_profile)
            features = prepare_document(document, request_profile)
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
                api_url=_api_url_for_profile(
                    runtime_settings.api_url,
                    resolved_profile,
                    request_profile,
                ),
            )
        except UpstreamImportError as err:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": f"{request_profile.title} API upsert failed",
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


def _normalize_upload(
    document: Any,
    filename: str | None,
    profile: ImportProfile,
) -> Any:
    """Convert classic GeoJSON uploads; leave JSON-FG uploads unchanged."""
    if not _is_classic_geojson_filename(filename):
        return document
    return convert_document(document, profile=profile)


def _profile_from_env() -> ImportProfile:
    profile_name = os.environ.get(PROFILE_ENV_NAME, BANE_PROFILE.name)
    try:
        return get_profile(profile_name)
    except ValueError as err:
        supported = ", ".join(sorted(BUILTIN_PROFILES))
        raise ValueError(f"{PROFILE_ENV_NAME} must be one of: {supported}") from err


def _request_profile(
    profile_name: str | None,
    default_profile: ImportProfile,
) -> ImportProfile:
    if profile_name is None:
        return default_profile
    try:
        return get_profile(profile_name)
    except ValueError as err:
        supported = ", ".join(sorted(BUILTIN_PROFILES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"profile must be one of: {supported}",
        ) from err


def _api_url_for_profile(
    configured_api_url: str,
    default_profile: ImportProfile,
    request_profile: ImportProfile,
) -> str:
    if request_profile.name == default_profile.name:
        return configured_api_url.rstrip("/")

    override_name = f"GCIMPORT_API_URL_{request_profile.name.upper()}"
    override_value = os.environ.get(override_name)
    if override_value is not None and override_value.strip():
        return override_value.strip().rstrip("/")

    configured = urlsplit(configured_api_url)
    target = urlsplit(request_profile.default_api_url)
    return urlunsplit(
        (
            configured.scheme,
            configured.netloc,
            target.path,
            target.query,
            target.fragment,
        )
    ).rstrip("/")


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
