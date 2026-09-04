import pytest
from pygeoapi.process.base import ProcessorExecuteError

from geocomponents.processes.delete_collection_items import (
    DeleteCollectionItemsProcessor,
)


class _FakeProvider:
    def __init__(self, provider_def):
        self.provider_def = provider_def

    def delete_all(self):
        return 23


def _processor():
    return DeleteCollectionItemsProcessor(
        {
            "name": "geocomponents.processes.delete_collection_items.DeleteCollectionItemsProcessor",
            "provider_defs": {"bygning": {"collection": "bygning"}},
        }
    )


def test_execute_returns_deleted_count(monkeypatch):
    monkeypatch.setattr(
        "geocomponents.processes.delete_collection_items.DbFunctionProvider",
        _FakeProvider,
    )

    mimetype, payload = _processor().execute({"collection": "bygning"})

    assert mimetype == "application/json"
    assert payload == {"collection": "bygning", "deleted": 23}


@pytest.mark.parametrize("collection", [None, "", "unknown"])
def test_execute_rejects_invalid_collection(collection):
    with pytest.raises(ProcessorExecuteError):
        _processor().execute({"collection": collection})
