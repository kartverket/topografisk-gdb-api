from __future__ import annotations

from typing import Any


def link(
    *, href: str, rel: str, title: str | None = None, media_type: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"href": href, "rel": rel}
    if title is not None:
        payload["title"] = title
    if media_type is not None:
        payload["type"] = media_type
    return payload
