from pygeoapi.provider.base import ProviderItemNotFoundError

from geocomponents.processes.transaction_batch_upsert import (
    TransactionBatchUpsertProcessor,
)
from geocomponents.processes.upsert_batch import UpsertBatchProcessor


class _FakeProvider:
    def __init__(self, provider_def):
        self.provider_def = provider_def

    def upsert_many(self, features):
        assert len(features) == 2
        return [
            "11111111-1111-1111-1111-111111111111",
            "22222222-2222-2222-2222-222222222222",
        ]


class _FakeTransactionProvider:
    def __init__(self, provider_def):
        self.provider_def = provider_def

    def get(self, identifier, **kwargs):
        if identifier == "11111111-1111-1111-1111-111111111111":
            return {"id": identifier}
        raise ProviderItemNotFoundError("missing")

    def transaction(self, document):
        assert document == {
            "semantic": "atomic",
            "transaction": [
                {
                    "action": "replace",
                    "collection": "bygning",
                    "id": "11111111-1111-1111-1111-111111111111",
                    "feature": {
                        "id": "11111111-1111-1111-1111-111111111111",
                        "type": "Feature",
                        "properties": {"lokalid": "a"},
                    },
                },
                {
                    "action": "insert",
                    "collection": "bygning",
                    "feature": {
                        "id": "22222222-2222-2222-2222-222222222222",
                        "type": "Feature",
                        "properties": {"lokalid": "b"},
                    },
                },
            ],
        }
        return {
            "committed": True,
            "phase": "items",
            "reason": None,
            "items": [
                {"id": "11111111-1111-1111-1111-111111111111"},
                {"id": "22222222-2222-2222-2222-222222222222"},
            ],
            "structure": [],
            "geometry": [],
        }


def test_execute_returns_declared_outputs(monkeypatch):
    processor = UpsertBatchProcessor(
        {
            "name": "geocomponents.processes.upsert_batch.UpsertBatchProcessor",
            "provider_defs": {
                "bygning": {"collection": "bygning"},
            },
        }
    )
    monkeypatch.setattr(
        "geocomponents.processes.upsert_batch.DbFunctionProvider", _FakeProvider
    )

    mimetype, payload = processor.execute(
        {
            "collection": "bygning",
            "features": [
                {"type": "Feature", "properties": {"lokalid": "a"}},
                {"type": "Feature", "properties": {"lokalid": "b"}},
            ],
        }
    )

    assert mimetype == "application/json"
    assert payload == {
        "collection": "bygning",
        "total": 2,
        "features": [
            {"id": "11111111-1111-1111-1111-111111111111"},
            {"id": "22222222-2222-2222-2222-222222222222"},
        ],
    }


def test_transaction_execute_returns_declared_outputs(monkeypatch):
    processor = TransactionBatchUpsertProcessor(
        {
            "name": "geocomponents.processes.transaction_batch_upsert.TransactionBatchUpsertProcessor",
            "provider_defs": {
                "bygning": {"collection": "bygning"},
            },
        }
    )
    monkeypatch.setattr(
        "geocomponents.processes.transaction_batch_upsert.DbFunctionProvider",
        _FakeTransactionProvider,
    )

    mimetype, payload = processor.execute(
        {
            "collection": "bygning",
            "features": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "Feature",
                    "properties": {"lokalid": "a"},
                },
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "type": "Feature",
                    "properties": {"lokalid": "b"},
                },
            ],
        }
    )

    assert mimetype == "application/json"
    assert payload == {
        "collection": "bygning",
        "total": 2,
        "features": [
            {"id": "11111111-1111-1111-1111-111111111111"},
            {"id": "22222222-2222-2222-2222-222222222222"},
        ],
    }
