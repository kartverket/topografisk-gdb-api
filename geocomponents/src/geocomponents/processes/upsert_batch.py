"""Dataset-scoped batch upsert via OGC API - Processes."""

from __future__ import annotations

from copy import deepcopy

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from geocomponents.api.db_function_provider import DbFunctionProvider

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "upsert-batch",
    "title": {"en": "Batch upsert features"},
    "description": {
        "en": "Upsert a batch of GeoJSON Features into one upsertable collection."
    },
    "jobControlOptions": ["sync-execute"],
    "keywords": ["upsert", "batch", "features"],
    "links": [],
    "inputs": {
        "collection": {
            "title": "Collection",
            "description": "Target collection id.",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
        "features": {
            "title": "Features",
            "description": "GeoJSON Features to upsert.",
            "schema": {
                "type": "array",
                "items": {"type": "object"},
            },
            "minOccurs": 1,
            "maxOccurs": 1,
        },
    },
    "outputs": {
        "collection": {
            "title": "Collection",
            "description": "Collection the batch upsert targeted.",
            "schema": {"type": "string"},
        },
        "total": {
            "title": "Total",
            "description": "Number of inserted or replaced features.",
            "schema": {"type": "integer"},
        },
        "features": {
            "title": "Features",
            "description": "Stable ids for the inserted or replaced features.",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string", "format": "uuid"}},
                },
            },
        },
    },
    "example": {
        "inputs": {
            "collection": "example_collection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [10.0, 60.0]},
                    "properties": {"lokalid": "example-1"},
                }
            ],
        }
    },
}


class UpsertBatchProcessor(BaseProcessor):
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
        features = data.get("features")

        if not isinstance(collection, str) or not collection:
            raise ProcessorExecuteError("input 'collection' must be a non-empty string")
        provider_def = self._provider_defs.get(collection)
        if provider_def is None:
            raise ProcessorExecuteError(
                f"collection '{collection}' is not enabled for batch upsert"
            )
        if not isinstance(features, list) or not features:
            raise ProcessorExecuteError("input 'features' must be a non-empty array")

        provider = DbFunctionProvider(provider_def)
        identifiers = provider.upsert_many(features)
        return "application/json", {
            "collection": collection,
            "total": len(identifiers),
            "features": [{"id": identifier} for identifier in identifiers],
        }

    def __repr__(self):
        return "<UpsertBatchProcessor>"
