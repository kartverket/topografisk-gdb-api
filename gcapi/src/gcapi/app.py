from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from gcapi import __version__
from gcapi.auth import InMemorySessionStore
from gcapi.config import SERVICE_NAME, Settings
from gcapi.problems import problem_response
from gcapi.transport import build_runtime_client, proxy_request

PROXY_METHODS = ["GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"]
GCJOBS_PROXY_PATH_RE = re.compile(
    r"^datasets/[^/]+/ogc_api/(?:processes/import|jobs)(?:/.*)?$"
)
PUBLIC_PATHS = frozenset({"/healthz"})


def _upstream_base_url(application: FastAPI, proxy_path: str) -> str:
    gcjobs_url = application.state.settings.gcjobs_url
    if gcjobs_url and GCJOBS_PROXY_PATH_RE.match(proxy_path.lstrip("/")):
        return gcjobs_url.rstrip("/")
    return application.state.settings.geocomponents_url.rstrip("/")


def _upstream_url(application: FastAPI, proxy_path: str) -> str:
    base_url = _upstream_base_url(application, proxy_path)
    if not proxy_path:
        return base_url
    return f"{base_url}/{proxy_path.lstrip('/')}"


async def _authenticate(
    application: FastAPI, request: Request
) -> tuple[bool, str | None]:
    session_cookie_name = application.state.settings.session_cookie_name
    session_id = request.cookies.get(session_cookie_name)
    if session_id:
        session = application.state.session_store.get(session_id)
        if session is not None:
            return True, None
        application.state.session_store.delete(session_id)

    try:
        auth_response = await application.state.http_client.get(
            f"{application.state.settings.gccore_url}/auth"
        )
    except httpx2.TimeoutException as err:
        raise RuntimeError("Timed out contacting auth endpoint") from err
    except httpx2.HTTPError as err:
        raise RuntimeError(f"Could not contact auth endpoint: {err}") from err

    if auth_response.is_success:
        try:
            payload = auth_response.json()
        except ValueError as err:
            raise RuntimeError("Auth endpoint returned invalid JSON") from err
        if payload.get("authorized") is True:
            session = application.state.session_store.create(
                ttl_seconds=application.state.settings.session_ttl_seconds
            )
            return True, session.session_id
        return False, None

    if auth_response.status_code in {401, 403}:
        return False, None

    raise RuntimeError(
        f"Auth endpoint returned unexpected status {auth_response.status_code}"
    )


async def _authentication_middleware(
    application: FastAPI,
    request: Request,
    call_next,
) -> Response:
    if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    try:
        authenticated, new_session_id = await _authenticate(application, request)
    except RuntimeError as err:
        return problem_response(
            status_code=503,
            title="Authentication unavailable",
            detail=str(err),
        )

    if not authenticated:
        return problem_response(
            status_code=401,
            title="Authentication required",
            detail="Request could not be authenticated",
        )

    response = await call_next(request)
    if new_session_id is not None:
        response.set_cookie(
            key=application.state.settings.session_cookie_name,
            value=new_session_id,
            max_age=application.state.settings.session_ttl_seconds,
            httponly=True,
            samesite=application.state.settings.session_cookie_samesite,
            secure=application.state.settings.session_cookie_secure,
        )
    return response


def create_app(
    *,
    settings: Settings | None = None,
    client: httpx2.AsyncClient | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resolved_settings = settings or Settings.from_env()
        application.state.settings = resolved_settings
        application.state.session_store = InMemorySessionStore()
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

    async def _proxy(request: Request, proxy_path: str):
        return await proxy_request(
            client=application.state.http_client,
            request=request,
            upstream_url=_upstream_url(application, proxy_path),
            max_upload_bytes=application.state.settings.max_upload_bytes,
        )

    @application.middleware("http")
    async def authentication_middleware(request: Request, call_next) -> Response:
        return await _authentication_middleware(application, request, call_next)

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
