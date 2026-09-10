from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

import psycopg
from redis.asyncio import Redis

LOGGER = logging.getLogger(__name__)
STREAM_PREFIX = "geocomponents.feature-events"


@dataclass(frozen=True)
class ChangeEvent:
    id: UUID
    dataset: str
    collection: str
    localids: tuple[UUID, ...]
    operations: tuple[str, ...]
    srid: int
    bbox: tuple[float, float, float, float] | None
    occurred_at: datetime

    def payload(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "type": "features.changed",
            "dataset": self.dataset,
            "maplayer": self.collection,
            "localids": [str(localid) for localid in self.localids],
            "operations": list(self.operations),
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "crs": f"http://www.opengis.net/def/crs/EPSG/0/{self.srid}",
            "occurred_at": self.occurred_at.isoformat(),
        }


def stream_name(dataset: str, collection: str) -> str:
    return f"{STREAM_PREFIX}.{dataset}.{collection}"


class EventPublisher(Protocol):
    async def publish(self, event: ChangeEvent) -> str: ...

    async def aclose(self) -> None: ...


class OutboxStore(Protocol):
    async def claim(self, *, limit: int, stale_after: float) -> list[ChangeEvent]: ...

    async def mark_published(self, event_id: UUID, message_id: str) -> None: ...

    async def mark_failed(self, event_id: UUID, error: str) -> None: ...

    async def aclose(self) -> None: ...


class RedisEventPublisher:
    def __init__(self, redis_url: str, *, maxlen: int) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._maxlen = maxlen

    async def publish(self, event: ChangeEvent) -> str:
        return await self._client.xadd(
            stream_name(event.dataset, event.collection),
            {"event": json.dumps(event.payload(), separators=(",", ":"))},
            maxlen=self._maxlen,
            approximate=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class PostgresOutboxStore:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._connection: psycopg.AsyncConnection | None = None
        self._claim_token: UUID | None = None

    async def _connect(self) -> psycopg.AsyncConnection:
        if self._connection is None or self._connection.closed:
            self._connection = await psycopg.AsyncConnection.connect(self._dsn)
        return self._connection

    async def claim(self, *, limit: int, stale_after: float) -> list[ChangeEvent]:
        connection = await self._connect()
        self._claim_token = uuid4()
        async with connection.transaction():
            cursor = await connection.execute(
                """
                with candidates as (
                    select id
                    from geocomponents_event.change_outbox
                    where published_at is null
                      and (claimed_at is null or claimed_at < now() - (%s * interval '1 second'))
                    order by created_at, id
                    for update skip locked
                    limit %s
                )
                update geocomponents_event.change_outbox event
                set claimed_at = now(), claim_token = %s, attempts = attempts + 1
                from candidates
                where event.id = candidates.id
                returning event.id, event.dataset, event.collection,
                          event.localids, event.operations, event.srid,
                          case when event.affected_area is null then null else array[
                              ST_XMin(Box2D(event.affected_area)),
                              ST_YMin(Box2D(event.affected_area)),
                              ST_XMax(Box2D(event.affected_area)),
                              ST_YMax(Box2D(event.affected_area))
                          ] end,
                          event.created_at
                """,
                (stale_after, limit, self._claim_token),
            )
            rows = await cursor.fetchall()
        return [
            ChangeEvent(
                id=row[0],
                dataset=row[1],
                collection=row[2],
                localids=tuple(row[3]),
                operations=tuple(row[4]),
                srid=row[5],
                bbox=tuple(row[6]) if row[6] is not None else None,
                occurred_at=row[7],
            )
            for row in rows
        ]

    async def mark_published(self, event_id: UUID, message_id: str) -> None:
        connection = await self._connect()
        async with connection.transaction():
            await connection.execute(
                """
                update geocomponents_event.change_outbox
                set published_at = now(), redis_message_id = %s,
                    claim_token = null, claimed_at = null, last_error = null
                where id = %s and claim_token = %s and published_at is null
                """,
                (message_id, event_id, self._claim_token),
            )

    async def mark_failed(self, event_id: UUID, error: str) -> None:
        connection = await self._connect()
        async with connection.transaction():
            await connection.execute(
                """
                update geocomponents_event.change_outbox
                set claim_token = null, claimed_at = null, last_error = %s
                where id = %s and claim_token = %s and published_at is null
                """,
                (error[:2000], event_id, self._claim_token),
            )

    async def aclose(self) -> None:
        if self._connection is not None:
            await self._connection.close()


class OutboxRelay:
    def __init__(
        self,
        store: OutboxStore,
        publisher: EventPublisher,
        *,
        poll_seconds: float,
        batch_size: int,
        stale_after: float,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._poll_seconds = poll_seconds
        self._batch_size = batch_size
        self._stale_after = stale_after

    async def run_once(self) -> int:
        events = await self._store.claim(
            limit=self._batch_size, stale_after=self._stale_after
        )
        for event in events:
            try:
                message_id = await self._publisher.publish(event)
                await self._store.mark_published(event.id, message_id)
            except Exception as err:
                LOGGER.exception("Failed to publish feature event %s", event.id)
                await self._store.mark_failed(event.id, str(err))
        return len(events)

    async def run(self) -> None:
        while True:
            try:
                count = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Feature event relay iteration failed")
                count = 0
            if count < self._batch_size:
                await asyncio.sleep(self._poll_seconds)

    async def aclose(self) -> None:
        await self._publisher.aclose()
        await self._store.aclose()
