from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from geocomponents.events import (
    ChangeEvent,
    OutboxRelay,
    RedisEventPublisher,
    stream_name,
)
from geocomponents.gateway.mounter import build_gateway

EVENT_ID = UUID("00000000-0000-0000-0000-000000000001")
LOCAL_ID = UUID("00000000-0000-0000-0000-000000000002")


def _event() -> ChangeEvent:
    return ChangeEvent(
        id=EVENT_ID,
        dataset="bygning",
        collection="bygning_posisjon",
        localids=(LOCAL_ID,),
        operations=("update",),
        srid=5972,
        bbox=(1.0, 2.0, 3.0, 4.0),
        occurred_at=datetime(2026, 9, 4, 12, tzinfo=UTC),
    )


class StubStore:
    def __init__(self, events: list[ChangeEvent]) -> None:
        self.events = events
        self.claim_args = None
        self.published = []
        self.failed = []
        self.closed = False

    async def claim(self, *, limit: int, stale_after: float) -> list[ChangeEvent]:
        self.claim_args = (limit, stale_after)
        return self.events

    async def mark_published(self, event_id, message_id) -> None:
        self.published.append((event_id, message_id))

    async def mark_failed(self, event_id, error) -> None:
        self.failed.append((event_id, error))

    async def aclose(self) -> None:
        self.closed = True


class StubPublisher:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.events = []
        self.closed = False

    async def publish(self, event: ChangeEvent) -> str:
        self.events.append(event)
        if self.error is not None:
            raise self.error
        return "1-0"

    async def aclose(self) -> None:
        self.closed = True


class StubRedis:
    def __init__(self) -> None:
        self.calls = []
        self.closed = False

    async def xadd(self, stream, fields, *, maxlen, approximate):
        self.calls.append((stream, fields, maxlen, approximate))
        return "7-0"

    async def aclose(self) -> None:
        self.closed = True


class StubRelay:
    def __init__(self) -> None:
        self.started = False
        self.cancelled = False
        self.closed = False

    async def run(self) -> None:
        self.started = True
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True

    async def aclose(self) -> None:
        self.closed = True


def test_event_payload_uses_native_crs_and_aggregate_bbox():
    assert stream_name("bygning", "bygning_posisjon") == (
        "geocomponents.feature-events.bygning.bygning_posisjon"
    )
    assert _event().payload() == {
        "id": str(EVENT_ID),
        "type": "features.changed",
        "dataset": "bygning",
        "maplayer": "bygning_posisjon",
        "localids": [str(LOCAL_ID)],
        "operations": ["update"],
        "bbox": [1.0, 2.0, 3.0, 4.0],
        "crs": "http://www.opengis.net/def/crs/EPSG/0/5972",
        "occurred_at": "2026-09-04T12:00:00+00:00",
    }


@pytest.mark.anyio
async def test_redis_publisher_adds_one_json_entry_to_maplayer_stream(monkeypatch):
    redis = StubRedis()
    monkeypatch.setattr(
        "geocomponents.events.Redis.from_url", lambda *_args, **_kwargs: redis
    )
    publisher = RedisEventPublisher("redis://unused", maxlen=500)

    assert await publisher.publish(_event()) == "7-0"

    stream, fields, maxlen, approximate = redis.calls[0]
    assert stream == "geocomponents.feature-events.bygning.bygning_posisjon"
    assert '"localids":["00000000-0000-0000-0000-000000000002"]' in fields["event"]
    assert maxlen == 500
    assert approximate is True


@pytest.mark.anyio
async def test_relay_marks_successful_publish():
    store = StubStore([_event()])
    publisher = StubPublisher()
    relay = OutboxRelay(store, publisher, poll_seconds=1, batch_size=25, stale_after=30)

    assert await relay.run_once() == 1

    assert store.claim_args == (25, 30)
    assert publisher.events == [_event()]
    assert store.published == [(EVENT_ID, "1-0")]
    assert store.failed == []


@pytest.mark.anyio
async def test_relay_releases_failed_event_for_retry():
    store = StubStore([_event()])
    publisher = StubPublisher(RuntimeError("redis unavailable"))
    relay = OutboxRelay(store, publisher, poll_seconds=1, batch_size=25, stale_after=30)

    assert await relay.run_once() == 1

    assert store.published == []
    assert store.failed == [(EVENT_ID, "redis unavailable")]


@pytest.mark.anyio
async def test_relay_closes_store_and_publisher():
    store = StubStore([])
    publisher = StubPublisher()
    relay = OutboxRelay(store, publisher, poll_seconds=1, batch_size=25, stale_after=30)

    await relay.aclose()

    assert store.closed is True
    assert publisher.closed is True


def test_gateway_lifespan_runs_and_closes_relay():
    relay = StubRelay()
    app = build_gateway([], object(), "http://localhost", event_relay=relay)

    with TestClient(app):
        assert relay.started is True

    assert relay.cancelled is True
    assert relay.closed is True
