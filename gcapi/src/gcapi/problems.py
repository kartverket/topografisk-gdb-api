from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def problem_response(
    *,
    status_code: int,
    title: str,
    detail: str,
    type_url: str = "about:blank",
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": type_url,
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if extra:
        payload.update(extra)
    return JSONResponse(
        payload,
        status_code=status_code,
        media_type="application/problem+json",
    )
