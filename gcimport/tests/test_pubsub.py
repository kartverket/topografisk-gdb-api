from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from gcimport.app import create_app
from gcimport.config import Settings
from gcimport.pubsub import RedisImportEventPublisher


class _FakeRedisClient:
    def __init__(self) -> None:
        self.xadd_calls: list[dict[str, Any]] = []
        self.closed = False

    async def xadd(
        self,
        stream: str,
        fields: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> None:
        self.xadd_calls.append(
            {
                "stream": stream,
                "fields": fields,
                "maxlen": maxlen,
                "approximate": approximate,
            }
        )

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedisModule:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client
        self.from_url_calls: list[dict[str, Any]] = []

    def from_url(self, redis_url: str, *, decode_responses: bool) -> _FakeRedisClient:
        self.from_url_calls.append(
            {
                "redis_url": redis_url,
                "decode_responses": decode_responses,
            }
        )
        return self._client


class _ClosablePublisher:
    def __init__(self) -> None:
        self.closed = False

    async def publish(self, event: dict[str, Any]) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True


class _FakeAsyncClient:
    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


@pytest.mark.asyncio
async def test_redis_import_event_publisher_reuses_one_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeRedisClient()
    redis_module = _FakeRedisModule(client)
    monkeypatch.setattr(
        "gcimport.pubsub._redis_asyncio_module",
        lambda: redis_module,
    )

    publisher = RedisImportEventPublisher("redis://redis:6379/0", stream="events")

    await publisher.publish({"event": "import.started", "import_id": "one"})
    await publisher.publish({"event": "import.completed", "import_id": "one"})
    await publisher.aclose()

    assert redis_module.from_url_calls == [
        {"redis_url": "redis://redis:6379/0", "decode_responses": True}
    ]
    assert len(client.xadd_calls) == 2
    assert [call["stream"] for call in client.xadd_calls] == ["events", "events"]
    assert client.closed is True


def test_create_app_closes_event_publisher_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publisher = _ClosablePublisher()
    monkeypatch.setattr("gcimport.app.httpx2.AsyncClient", _FakeAsyncClient)

    app = create_app(
        settings=Settings(
            geocomponents_api_url="https://components.example",
            redis_url="redis://redis:6379/0",
        ),
        event_publisher=publisher,
    )

    with TestClient(app):
        pass

    assert publisher.closed is True
