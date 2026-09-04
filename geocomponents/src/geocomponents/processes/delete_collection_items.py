"""Delete all features in a collection via OGC API - Processes."""

from __future__ import annotations

from copy import deepcopy

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from geocomponents.api.db_function_provider import DbFunctionProvider

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "delete-collection-items",
    "title": {"en": "Delete all collection items"},
    "description": {
        "en": "Delete every feature in one writable collection as a single database transaction."
    },
    "jobControlOptions": ["sync-execute"],
    "keywords": ["delete", "collection", "features"],
    "links": [],
    "inputs": {
        "collection": {
            "title": "Collection",
            "description": "Writable collection to empty.",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        }
    },
    "outputs": {
        "collection": {
            "title": "Collection",
            "description": "Collection that was emptied.",
            "schema": {"type": "string"},
        },
        "deleted": {
            "title": "Deleted features",
            "description": "Number of deleted features.",
            "schema": {"type": "integer"},
        },
    },
    "example": {"inputs": {"collection": "example_collection"}},
}


class DeleteCollectionItemsProcessor(BaseProcessor):
    def __init__(self, processor_def):
        metadata = deepcopy(PROCESS_METADATA)
        provider_defs = processor_def.get("provider_defs", {})
        allowed = sorted(provider_defs)
        metadata["inputs"]["collection"]["schema"] = {
            "type": "string",
            "enum": allowed,
        }
        if allowed:
            metadata["example"]["inputs"]["collection"] = allowed[0]
        super().__init__(processor_def, metadata)
        self._provider_defs = provider_defs

    def execute(self, data, outputs=None):
        collection = data.get("collection")
        if not isinstance(collection, str) or not collection:
            raise ProcessorExecuteError("input 'collection' must be a non-empty string")
        provider_def = self._provider_defs.get(collection)
        if provider_def is None:
            raise ProcessorExecuteError(
                f"collection '{collection}' is not enabled for complete deletion"
            )

        deleted = DbFunctionProvider(provider_def).delete_all()
        return "application/json", {
            "collection": collection,
            "deleted": deleted,
        }

    def __repr__(self):
        return "<DeleteCollectionItemsProcessor>"
