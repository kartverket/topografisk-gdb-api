from __future__ import annotations

from collections.abc import AsyncIterator

import httpx2
from fastapi import HTTPException, Request
from fastapi.responses import Response

from gcapi.config import Settings
from gcapi.problems import problem_response

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


def _response_headers(
    response: httpx2.Response,
    *,
    override_content_length: bool,
) -> dict[str, str]:
    headers = filter_hop_by_hop_headers(response.headers)
    if override_content_length:
        headers.pop("content-length", None)
    return headers


async def proxy_request(
    *,
    client: httpx2.AsyncClient,
    request: Request,
    upstream_url: str,
    max_upload_bytes: int,
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

    body = await upstream_response.aread()
    content_type = upstream_response.headers.get("content-type")
    await upstream_response.aclose()
    return Response(
        content=body,
        status_code=upstream_response.status_code,
        headers=_response_headers(
            upstream_response,
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
