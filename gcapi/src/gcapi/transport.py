from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx2
from fastapi import HTTPException, Request
from fastapi.responses import Response

from gcapi.catalog import CatalogSnapshot
from gcapi.config import Settings
from gcapi.problems import problem_response
from gcapi.rewrite import rewrite_document, rewrite_href

HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


def build_runtime_client(settings: Settings) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        trust_env=False,
        timeout=httpx2.Timeout(
            settings.request_timeout_seconds,
            connect=settings.connect_timeout_seconds,
        ),
    )


def filter_hop_by_hop_headers(
    headers: httpx2.Headers | dict[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }


def _should_rewrite_json(content_type: str | None) -> bool:
    if content_type is None:
        return False
    normalized = content_type.lower()
    return (
        "application/json" in normalized
        or "application/geo+json" in normalized
        or "application/problem+json" in normalized
    )


def _response_headers(  # noqa: PLR0913
    response: httpx2.Response,
    *,
    settings: Settings,
    catalog: CatalogSnapshot,
    upstream_base_url: str,
    public_api_base_path: str | None,
    override_content_length: bool,
) -> dict[str, str]:
    headers = filter_hop_by_hop_headers(response.headers)
    if "location" in {key.lower() for key in headers}:
        for key, value in list(headers.items()):
            if key.lower() == "location":
                headers[key] = rewrite_href(
                    value,
                    settings=settings,
                    catalog=catalog,
                    upstream_base_url=upstream_base_url,
                    public_api_base_path=public_api_base_path,
                )
    if override_content_length:
        headers.pop("content-length", None)
    return headers


async def proxy_request(  # noqa: PLR0913
    *,
    client: httpx2.AsyncClient,
    request: Request,
    upstream_url: str,
    settings: Settings,
    catalog: CatalogSnapshot,
    max_upload_bytes: int,
    public_api_base_path: str | None = None,
) -> Response:
    headers = filter_hop_by_hop_headers(request.headers)
    headers.pop("host", None)
    content: AsyncIterator[bytes] | None = None
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        content = bounded_request_stream(request, max_bytes=max_upload_bytes)

    upstream_request = client.build_request(
        request.method,
        upstream_url,
        params=list(request.query_params.multi_items()),
        headers=headers,
        content=content,
    )

    try:
        upstream_response = await client.send(upstream_request, stream=True)
    except httpx2.TimeoutException:
        return problem_response(
            status_code=504,
            title="Upstream timeout",
            detail=f"Timed out contacting upstream at {upstream_url}",
        )
    except httpx2.HTTPError as err:
        return problem_response(
            status_code=502,
            title="Upstream unavailable",
            detail=f"Could not contact upstream at {upstream_url}: {err}",
        )

    content_type = upstream_response.headers.get("content-type")
    if _should_rewrite_json(content_type):
        body = await upstream_response.aread()
        await upstream_response.aclose()
        try:
            payload = json.loads(body)
        except ValueError:
            return problem_response(
                status_code=502,
                title="Malformed upstream response",
                detail=f"Upstream returned invalid JSON from {upstream_url}",
            )
        rewritten = rewrite_document(
            payload,
            settings=settings,
            catalog=catalog,
            upstream_base_url=upstream_url,
            public_api_base_path=public_api_base_path,
        )
        encoded = json.dumps(rewritten).encode("utf-8")
        return Response(
            content=encoded,
            status_code=upstream_response.status_code,
            headers=_response_headers(
                upstream_response,
                settings=settings,
                catalog=catalog,
                upstream_base_url=upstream_url,
                public_api_base_path=public_api_base_path,
                override_content_length=True,
            ),
            media_type=content_type,
        )

    body = await upstream_response.aread()
    await upstream_response.aclose()
    return Response(
        content=body,
        status_code=upstream_response.status_code,
        headers=_response_headers(
            upstream_response,
            settings=settings,
            catalog=catalog,
            upstream_base_url=upstream_url,
            public_api_base_path=public_api_base_path,
            override_content_length=True,
        ),
        media_type=content_type,
    )


async def bounded_request_stream(
    request: Request,
    *,
    max_bytes: int,
) -> AsyncIterator[bytes]:
    total_bytes = 0
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(status_code=413, detail="upload exceeds size limit")
        except ValueError:
            pass

    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(status_code=413, detail="upload exceeds size limit")
        if chunk:
            yield chunk
