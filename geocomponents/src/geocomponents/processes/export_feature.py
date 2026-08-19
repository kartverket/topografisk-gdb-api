from pygeoapi.process.base import BaseProcessor
from geocomponents.config import database_dsn
import psycopg
import orjson

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "export-feature",
    "title": {"en": "Export Feature"},
    "description": {"en": "Export a feature to a file."},
    "jobControlOptions": ["sync-execute"],
    "keywords": ["export"],
    "links": [],
    "inputs": {
        "collection": {
            "title": "Collection",
            "description": "The collection to export the feature from.",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
        "feature_id": {
            "title": "Feature ID",
            "description": "The ID of the feature to export.",
            "schema": {"type": "string"},
            "minOccurs": 1,
            "maxOccurs": 1,
        },
    },
    "outputs": {
        "result": {
            "title": "Result",
            "schema": {"type": "object"},
        },
    },
    "example": {
        "inputs": {"collection": "parcels", "feature_id": "123"},
    }
}

class ExportFeatureProcessor(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)
        self.dataset = processor_def["dataset"]

    def execute(self, data, outputs=None):
        collection = data["collection"]
        feature_id = data["feature_id"]

        with psycopg.connect(database_dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_item(%s, %s, %s)",
                (self.dataset, collection, feature_id),
            )
            row = cur.fetchone()
            payload = row[0] if row else None
            if payload is None:
                raise ValueError(f"Feature {feature_id} not found in {self.dataset}/{collection}")
            
            body_bytes = orjson.dumps(payload)
            filename = f"{collection}-{feature_id}.geojson"

        return "application/geo+json", body_bytes


    def __repr__(self):
        return "<ExportFeatureProcessor>"
