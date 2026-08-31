"""Dataset-scoped atomic batch upsert via ``ogc.transaction``."""

from __future__ import annotations

from copy import deepcopy

from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError
from pygeoapi.provider.base import ProviderItemNotFoundError

from geocomponents.api.db_function_provider import DbFunctionProvider

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "transaction-batch-upsert",
    "title": {"en": "Atomic batch upsert features"},
    "description": {
        "en": "Atomically insert or replace a batch of GeoJSON Features into one upsertable collection. Each feature must include an id."
    },
    "jobControlOptions": ["sync-execute"],
    "keywords": ["transaction", "upsert", "batch", "features"],
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
            "description": "GeoJSON Features to atomically insert or replace.",
            "schema": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "string", "format": "uuid"}},
                },
            },
            "minOccurs": 1,
            "maxOccurs": 1,
        },
    },
    "outputs": {
        "collection": {
            "title": "Collection",
            "description": "Collection the atomic batch upsert targeted.",
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
                    "id": "11111111-1111-1111-1111-111111111111",
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [10.0, 60.0]},
                    "properties": {"lokalid": "example-1"},
                }
            ],
        }
    },
}


class TransactionBatchUpsertProcessor(BaseProcessor):
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
                f"collection '{collection}' is not enabled for transaction batch upsert"
            )
        if not isinstance(features, list) or not features:
            raise ProcessorExecuteError("input 'features' must be a non-empty array")

        provider = DbFunctionProvider(provider_def)
        transaction_items = []
        for index, feature in enumerate(features):
            if not isinstance(feature, dict):
                raise ProcessorExecuteError(
                    f"input 'features[{index}]' must be a GeoJSON Feature object"
                )
            feature_id = feature.get("id")
            if not isinstance(feature_id, str) or not feature_id:
                raise ProcessorExecuteError(
                    f"input 'features[{index}].id' must be a non-empty string"
                )

            try:
                provider.get(feature_id)
            except ProviderItemNotFoundError:
                transaction_items.append(
                    {
                        "action": "insert",
                        "collection": collection,
                        "feature": feature,
                    }
                )
            else:
                transaction_items.append(
                    {
                        "action": "replace",
                        "collection": collection,
                        "id": feature_id,
                        "feature": feature,
                    }
                )

        report = provider.transaction(
            {"semantic": "atomic", "transaction": transaction_items}
        )
        if report.get("committed") is not True:
            reason = report.get("reason")
            if not reason:
                items = report.get("items")
                if isinstance(items, list) and items:
                    reason = items[0].get("reason")
            raise ProcessorExecuteError(reason or "transaction batch upsert failed")

        identifiers = [item["id"] for item in report.get("items", [])]
        return "application/json", {
            "collection": collection,
            "total": len(identifiers),
            "features": [{"id": identifier} for identifier in identifiers],
        }

    def __repr__(self):
        return "<TransactionBatchUpsertProcessor>"
