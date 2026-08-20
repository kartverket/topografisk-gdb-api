from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError
from geocomponents.config import database_dsn
import psycopg
import orjson


class FeatureNotFoundError(ProcessorExecuteError):
    """Raised when the requested feature does not exist."""

def _to_jsonfg(feature: dict) -> dict:
    return { 
        "type": "Feature",
        "id": feature.get("id"),
        "featureType": feature.get("properties", {}).get("objtype"),
        "geometry": feature.get("geometry"),
        "properties": feature.get("properties", {}),
    }

FORMATS = {
    "geojson": ("application/geo+json",  lambda f: orjson.dumps(f)),
    "jsonfg":  ("application/vnd.ogc.fg+json", lambda f: orjson.dumps(_to_jsonfg(f))),
}

PROCESS_METADATA = {
    "version": "0.1.0",
    "id": "export-feature",
    "title": {"en": "Export Feature"},
    "description": {"en": "Export a single feature as a downloadable file."},
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
        "format": {
            "title": "Output format",
            "description": "The output format of the exported feature.",
            "schema": {
                "type": "string", 
                "enum": ["geojson", "jsonfg"],
                "default": "geojson"},
            "minOccurs": 0,
            "maxOccurs": 1,
        }
    },
    "outputs": {
        "result": {
            "title": "Feature file",
            "description": "GeoJSON Feature file",
            "schema": {
                "type": "string",
                "format": "binary",
                "contentMediaType": "application/geo+json",
            },
        },
    },
    "example": {
        "inputs": {"collection": "parcels", "feature_id": "00000000-0000-0000-0000-000000000000"},
    },
}


class ExportFeatureProcessor(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)
        self.dataset = processor_def["dataset"]

    def execute(self, data, outputs=None):
        collection = data["collection"]
        feature_id = data["feature_id"]
        format_ = data.get("format", "geojson")

        with psycopg.connect(database_dsn()) as conn, conn.cursor() as cur:
            cur.execute(
                "select ogc.feature_item(%s, %s, %s)",
                (self.dataset, collection, feature_id),
            )
            row = cur.fetchone()
            payload = row[0] if row else None

        if payload is None:
            raise FeatureNotFoundError(
                f"Feature {feature_id} not found in {self.dataset}/{collection}"
            )
        
        try:
            media_type, encode = FORMATS[format_]
        except KeyError:
            raise ProcessorExecuteError(f"Unsupported format: {format_}")
            
        body_bytes = encode(payload)
        return media_type, body_bytes

    def __repr__(self):
        return "<ExportFeatureProcessor>"

