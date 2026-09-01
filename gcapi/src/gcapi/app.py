from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from cachetools import TTLCache
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from gcapi import __version__
from gcapi.config import SERVICE_NAME, Settings
from gcapi.problems import problem_response
from gcapi.transport import build_runtime_client, proxy_request

PROXY_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
GCJOBS_PROXY_PATH_RE = re.compile(
    r"^datasets/[^/]+/ogc_api/(?:processes/import|jobs)(?:/.*)?$"
)
AUTH_EXEMPT_PATHS = frozenset({"/healthz"})
AUTH_CACHE_TTL_SECONDS = 600
AUTH_CACHE_MAX_SIZE = 1024
HTTP_BAD_REQUEST = 400


class AuthorizationError(RuntimeError):
    def __init__(self, *, status_code: int, title: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.title = title
        self.detail = detail


def _client_id_for_request(request: Request) -> str | None:
    # Placeholder until the fronting reverse proxy injects authenticated client context.
    return None


def _authorization_cache_key(client_id: str | None) -> str:
    normalized_client_id = "none" if client_id is None else client_id
    return f"client_id:{normalized_client_id}"


async def _authorize_request(
    *, application: FastAPI, client_id: str | None, request: Request
) -> None:
    cache_key = _authorization_cache_key(client_id)
    auth_cache: TTLCache[str, bool] = application.state.authorization_cache
    if cache_key in auth_cache:
        request.state.client_id = client_id
        return

    authorize_url = f"{application.state.settings.gccore_url.rstrip('/')}/authorize"

    try:
        response = await application.state.http_client.post(
            authorize_url,
            json={"client_id": client_id},
        )
    except httpx2.TimeoutException as err:
        raise AuthorizationError(
            status_code=504,
            title="Authorization timeout",
            detail=f"Timed out contacting authorization service at {authorize_url}",
        ) from err
    except httpx2.HTTPError as err:
        raise AuthorizationError(
            status_code=502,
            title="Authorization unavailable",
            detail=f"Could not contact authorization service at {authorize_url}: {err}",
        ) from err

    if response.status_code >= HTTP_BAD_REQUEST:
        raise AuthorizationError(
            status_code=502,
            title="Authorization rejected",
            detail=(
                "Authorization service returned an unexpected status "
                f"{response.status_code}"
            ),
        )

    try:
        payload = response.json()
    except ValueError as err:
        raise AuthorizationError(
            status_code=502,
            title="Authorization rejected",
            detail="Authorization service returned invalid JSON",
        ) from err

    if not isinstance(payload, dict):
        raise AuthorizationError(
            status_code=502,
            title="Authorization rejected",
            detail="Authorization service returned an invalid response body",
        )

    if payload.get("authorized") is not True:
        raise AuthorizationError(
            status_code=401,
            title="Unauthorized",
            detail="Authorization service did not approve the request",
        )

    auth_cache[cache_key] = True
    request.state.client_id = client_id


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or Settings.from_env()
        application.state.settings = resolved_settings
        application.state.authorization_cache = TTLCache(
            maxsize=AUTH_CACHE_MAX_SIZE,
            ttl=AUTH_CACHE_TTL_SECONDS,
        )
        if client is not None:
            application.state.http_client = client
            yield
            return

        async with build_runtime_client(resolved_settings) as runtime_client:
            application.state.http_client = runtime_client
            yield

    application = FastAPI(
        title=SERVICE_NAME,
        version=__version__,
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Location",
            "Link",
            "ETag",
            "Content-Crs",
            "Preference-Applied",
        ],
    )

    @application.middleware("http")
    async def authorize_request_context(request: Request, call_next) -> Response:
        if request.method.upper() == "OPTIONS" or request.url.path in AUTH_EXEMPT_PATHS:
            return await call_next(request)

        try:
            await _authorize_request(
                application=application,
                client_id=_client_id_for_request(request),
                request=request,
            )
        except AuthorizationError as err:
            return problem_response(
                status_code=err.status_code,
                title=err.title,
                detail=err.detail,
            )
        return await call_next(request)

    def _upstream_base_url(proxy_path: str) -> str:
        gcjobs_url = application.state.settings.gcjobs_url
        if gcjobs_url and GCJOBS_PROXY_PATH_RE.match(proxy_path.lstrip("/")):
            return gcjobs_url.rstrip("/")
        return application.state.settings.geocomponents_url.rstrip("/")

    def _upstream_url(proxy_path: str) -> str:
        base_url = _upstream_base_url(proxy_path)
        if not proxy_path:
            return base_url
        return f"{base_url}/{proxy_path.lstrip('/')}"

    async def _proxy(request: Request, proxy_path: str):
        return await proxy_request(
            client=application.state.http_client,
            request=request,
            upstream_url=_upstream_url(proxy_path),
            max_upload_bytes=application.state.settings.max_upload_bytes,
        )

    @application.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "service": SERVICE_NAME}

    @application.api_route("/", methods=PROXY_METHODS)
    async def root_proxy(request: Request):
        return await _proxy(request, "")

    @application.api_route("/{proxy_path:path}", methods=PROXY_METHODS)
    async def catch_all_proxy(request: Request, proxy_path: str):
        return await _proxy(request, proxy_path)

    return application


app = create_app()
