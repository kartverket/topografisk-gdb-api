from __future__ import annotations

import json
import os
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol

IMPORT_EVENTS_STREAM = "gcimport.import-events"
IMPORT_EVENTS_GROUP = "gcjobs-import-events"
IMPORT_EVENTS_IDLE_MS = 30_000
IMPORT_EVENTS_READ_COUNT = 10
IMPORT_EVENTS_BLOCK_MS = 1_000


@dataclass(frozen=True)
class ImportEventMessage:
    event: dict[str, Any]
    _ack: Callable[[], Awaitable[None]] = field(repr=False)
    message_id: str | None = None

    async def ack(self) -> None:
        await self._ack()


class ImportEventListener(Protocol):
    async def messages(self) -> AsyncIterator[ImportEventMessage]: ...


class RedisImportEventListener:
    def __init__(
        self,
        redis_url: str,
        *,
        stream: str = IMPORT_EVENTS_STREAM,
        group: str = IMPORT_EVENTS_GROUP,
        consumer: str | None = None,
    ) -> None:
        self._redis_url = redis_url
        self._stream = stream
        self._group = group
        self._consumer = consumer or _default_consumer_name()

    async def messages(self) -> AsyncIterator[ImportEventMessage]:
        redis = _redis_asyncio_module()
        client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            await _ensure_stream_group(client, self._stream, self._group)
            pending_start_id = "0-0"
            while True:
                pending_start_id, pending_entries = await _claim_idle_entries(
                    client,
                    stream=self._stream,
                    group=self._group,
                    consumer=self._consumer,
                    start_id=pending_start_id,
                )
                if pending_entries:
                    for message_id, fields in pending_entries:
                        yield _stream_message(
                            client,
                            stream=self._stream,
                            group=self._group,
                            message_id=message_id,
                            fields=fields,
                        )
                    continue

                response = await client.xreadgroup(
                    groupname=self._group,
                    consumername=self._consumer,
                    streams={self._stream: ">"},
                    count=IMPORT_EVENTS_READ_COUNT,
                    block=IMPORT_EVENTS_BLOCK_MS,
                )
                for message_id, fields in _stream_entries(response):
                    yield _stream_message(
                        client,
                        stream=self._stream,
                        group=self._group,
                        message_id=message_id,
                        fields=fields,
                    )
        finally:
            await client.aclose()


class StubImportEventListener:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = [dict(event) for event in events]
        self.acked_events: list[dict[str, Any]] = []

    async def messages(self) -> AsyncIterator[ImportEventMessage]:
        for event in self._events:
            yield ImportEventMessage(
                event=event,
                message_id=None,
                _ack=self._acknowledger(event),
            )

    def _acknowledger(self, event: dict[str, Any]) -> Callable[[], Awaitable[None]]:
        async def acknowledge() -> None:
            self.acked_events.append(dict(event))

        return acknowledge


def _default_consumer_name() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


async def _ensure_stream_group(client: Any, stream: str, group: str) -> None:
    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception as err:
        if type(err).__name__ != "ResponseError" or "BUSYGROUP" not in str(err):
            raise


async def _claim_idle_entries(
    client: Any,
    *,
    stream: str,
    group: str,
    consumer: str,
    start_id: str,
) -> tuple[str, list[tuple[str, dict[str, str]]]]:
    response = await client.xautoclaim(
        stream,
        group,
        consumer,
        IMPORT_EVENTS_IDLE_MS,
        start_id=start_id,
        count=IMPORT_EVENTS_READ_COUNT,
    )
    next_start_id = response[0] if response else "0-0"
    entries = response[1] if len(response) > 1 else []
    return next_start_id, entries


def _stream_entries(
    response: list[tuple[str, list[tuple[str, dict[str, str]]]]],
) -> list[tuple[str, dict[str, str]]]:
    entries: list[tuple[str, dict[str, str]]] = []
    for _stream_name, stream_entries in response:
        entries.extend(stream_entries)
    return entries


def _stream_message(
    client: Any,
    *,
    stream: str,
    group: str,
    message_id: str,
    fields: dict[str, str],
) -> ImportEventMessage:
    payload = fields.get("event")
    if not isinstance(payload, str):
        raise ValueError("Redis stream entry missing event payload")
    decoded = json.loads(payload)
    if not isinstance(decoded, dict):
        raise ValueError("Redis stream event payload must decode to an object")

    async def acknowledge() -> None:
        await client.xack(stream, group, message_id)

    return ImportEventMessage(event=decoded, message_id=message_id, _ack=acknowledge)


def _redis_asyncio_module() -> Any:
    try:
        return import_module("redis.asyncio")
    except ModuleNotFoundError as err:
        raise RuntimeError(
            "Redis client dependency missing: install the `redis` package."
        ) from err
