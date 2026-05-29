import json
import logging
from collections import Counter
from pathlib import Path

import psycopg
import yaml
from pygeoapi.process.base import BaseProcessor, ProcessorExecuteError

from app.config import settings

LOGGER = logging.getLogger(__name__)

# process_descriptions/ lives at project root, not inside app/
# When deploying with Docker, ensure COPY process_descriptions/ is included
_PROCESS_DESC = (
    Path(__file__).parent.parent.parent
    / "process_descriptions"
    / "add_border_split_surface"
    / "process_description.yaml"
)

with _PROCESS_DESC.open() as _f:
    PROCESS_METADATA = yaml.safe_load(_f)


class AddBorderSplitSurfaceProcessor(BaseProcessor):
    def __init__(self, processor_def):
        super().__init__(processor_def, PROCESS_METADATA)
        self.supports_outputs = True

    def execute(self, data, outputs=None):
        feature_input = data.get("feature")
        if feature_input is None:
            raise ProcessorExecuteError("Missing required input: feature")

        # OGC Req 20: object inputs may arrive wrapped as {"value": ..., "mediaType": "..."}
        if isinstance(feature_input, dict) and "value" in feature_input:
            feature = feature_input["value"]
        else:
            feature = feature_input

        # The topology SQL function requires a GeoJSON "crs" member in the geometry.
        # Standard GeoJSON (RFC 7946) omits it, so inject EPSG:4326 if absent.
        # The SQL will ST_Transform to the topology's native SRID (4258) automatically.
        geom = feature.get("geometry", {})
        if geom and "crs" not in geom:
            geom["crs"] = {"type": "name", "properties": {"name": "EPSG:4326"}}
            feature = {**feature, "geometry": geom}

        want = set(outputs) if outputs else set(PROCESS_METADATA["outputs"])

        with psycopg.connect(settings.connection_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT fid, typ, act, frm"
                    " FROM topo_update.app_do_addborderssplitsurfaces('topo_ar5ngis', %s)",
                    (json.dumps(feature),),
                )
                changelog = [
                    {"fid": row[0], "typ": row[1], "act": row[2], "frm": row[3]}
                    for row in cur.fetchall()
                ]

                if "features" in want:
                    cur.execute(
                        "SELECT topo_ar5ngis.add_border_changes_as_geojson_fkb50_java(%s, 4326)",
                        (json.dumps(changelog),),
                    )
                    row = cur.fetchone()
                    features_text = row[0] if row else None

        result = {}

        if "changelog" in want:
            result["changelog"] = changelog

        if "features" in want:
            result["features"] = (
                json.loads(features_text)
                if features_text
                else {"type": "FeatureCollection", "features": []}
            )

        if "summary" in want:
            counts = Counter(row["act"] for row in changelog)
            result["summary"] = {
                "totalCreated": counts.get("C", 0),
                "totalModified": counts.get("M", 0),
                "totalDeleted": counts.get("D", 0),
                "totalSplit": counts.get("S", 0),
            }

        return "application/json", result

    def __repr__(self):
        return f"<AddBorderSplitSurfaceProcessor> {self.name}"
