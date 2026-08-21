from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Protocol

IMPORT_EVENTS_STREAM = "gcimport.import-events"  # This literal must remain identical in gcimport and gcjobs.
IMPORT_EVENTS_MAXLEN = 10_000


class ImportEventPublisher(Protocol):
    async def publish(self, event: dict[str, Any]) -> None: ...


class RedisImportEventPublisher:
    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = IMPORT_EVENTS_STREAM,
    ) -> None:
        self._stream = stream
        redis = _redis_asyncio_module()
        self._client = redis.from_url(redis_url, decode_responses=True)

    async def publish(self, event: dict[str, Any]) -> None:
        await self._client.xadd(
            self._stream,
            {"event": json.dumps(event)},
            maxlen=IMPORT_EVENTS_MAXLEN,
            approximate=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class RecordingImportEventPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))

    async def aclose(self) -> None:
        return None


def _redis_asyncio_module() -> Any:
    try:
        return import_module("redis.asyncio")
    except ModuleNotFoundError as err:
        raise RuntimeError(
            "Redis client dependency missing: install the `redis` package."
        ) from err
