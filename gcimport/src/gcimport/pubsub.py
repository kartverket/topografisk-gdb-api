from __future__ import annotations

import json
from importlib import import_module
from typing import Any, Protocol

IMPORT_EVENTS_STREAM = "gcimport.import-events"
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
        self._redis_url = redis_url
        self._stream = stream

    async def publish(self, event: dict[str, Any]) -> None:
        redis = _redis_asyncio_module()
        client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            await client.xadd(
                self._stream,
                {"event": json.dumps(event)},
                maxlen=IMPORT_EVENTS_MAXLEN,
                approximate=True,
            )
        finally:
            await client.aclose()


class RecordingImportEventPublisher:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


def _redis_asyncio_module() -> Any:
    try:
        return import_module("redis.asyncio")
    except ModuleNotFoundError as err:
        raise RuntimeError(
            "Redis client dependency missing: install the `redis` package."
        ) from err
