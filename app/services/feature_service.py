"""
Translates DAO results into GeoJSON for the route layer.

Both get_feature_geojson and get_feature_collection return orjson-serialised
bytes; routes wrap these with Response(content=..., media_type="application/geo+json").
"""

import datetime
from enum import Enum
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import orjson
from psycopg import Connection

import app.db.dao as dao  # noqa
from app.models.ogc import FeatureGeoJSON


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> bytes:
    model, geometry = await dao.get_feature(
        conn=conn, collection_id=collection_id, feature_id=feature_id
    )
    body = {
        "type": "Feature",
        "id": model.identifikasjon.lokal_id,
        "geometry": orjson.Fragment(geometry.encode()),
        "properties": model.model_dump(),
    }
    return orjson.dumps(body)


async def get_feature_collection(
    collection_id: str,
    bbox: str | None,
    datetime_query: str | None,
    limit: int | None,
    after_id: str | None,
    conn: Connection,
    request_url: str,
) -> dict:
    """Return a GeoJSON FeatureCollection serialised as bytes.

    The closing object includes numberReturned, timeStamp, and a rel:next link
    when the returned page is full.
    Byteserialisation is chosen to avoid round-tripping through stdlib JSON
    """
    # TODO: Implement other features, include type hinting
    rows = await dao.get_features(
        conn=conn, limit=limit, after_id=after_id, collection_id=collection_id
    )
    features = [
        {
            "type": "Feature",
            "id": model.identifikasjon.lokal_id,
            "geometry": orjson.Fragment(geometry.encode()),
            "properties": model.model_dump(),
        }
        for model, geometry in rows
    ]
    body = {
        "type": "FeatureCollection",
        "features": features,
        "numberReturned": len(features),
        "timeStamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    if limit is not None and len(features) == limit and features:
        last_id = features[-1]["id"]
        parsed = urlparse(request_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        params["after_id"] = [last_id]
        next_url = urlunparse(parsed._replace(query=urlencode(params, doseq=True)))
        body["links"] = [
            {"rel": "next", "href": next_url, "type": "application/geo+json"}
        ]
    return orjson.dumps(body)


async def patch_feature_geojson(
    collection_id: str, feature_id: str, patch: dict, conn: Connection
):
    model, _ = await dao.get_feature(conn, collection_id, feature_id)
    properties = model.model_dump()
    for key, value in patch.items():
        if isinstance(properties[key], Enum):
            properties[key] = type(properties[key])(value)
        else:
            properties[key] = value
    await dao.patch_nongeometry_attributes(properties, conn)


async def create_feature_geojson(
    collection_id: str, feature: FeatureGeoJSON, conn: Connection
):
    """splits feature into geometry and properties and forward
    to DAO for creation of object

    Changes required when dealing with topology
    """
    created_id = await dao.create_simple_feature(
        conn=conn,
        collection_id=collection_id,
        properties=feature.properties,
        geometry=feature.geometry,
    )
    return created_id
