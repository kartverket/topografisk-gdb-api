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
