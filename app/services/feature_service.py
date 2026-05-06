import datetime
from enum import Enum
from typing import AsyncGenerator

import orjson
from psycopg import Connection

import app.db.dao as dao  # noqa
from app.models.ogc import FeatureGeoJSON


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> FeatureGeoJSON:
    """Fetch a single feature and return it as a plain GeoJSON dict.

    Sketch function that fits the signature in FeatureService.
    """
    model, geometry = await dao.get_feature(
        conn=conn, collection_id=collection_id, feature_id=feature_id
    )
    return FeatureGeoJSON(
        id=model.identifikasjon.lokal_id,
        geometry=orjson.loads(geometry),
        properties=model.model_dump(),
    )


async def stream_feature_collection(
    collection_id: str,
    limit: int | None,
    after_id: str | None,
    conn: Connection,
    request_url: str,
) -> AsyncGenerator[bytes, None]:
    """Stream a GeoJSON FeatureCollection as bytes, one feature at a time.

    The closing object includes numberReturned, timeStamp, and a rel:next link
    when the returned page is full.
    """
    # TODO: Implement other features, include type hinting
    generator = dao.get_feature_collection(
        conn=conn, limit=limit, after_id=after_id, collection_id=collection_id
    )
    count = 0
    feature_id = None
    yield b'{"type":"FeatureCollection","features":['
    async for model, geometry in generator:
        if count:  # Add commas after first feature
            yield b","
        count += 1
        feature_id = model.identifikasjon.lokal_id
        feature_bytes = (
            b'{"type":"Feature", "id":'
            + orjson.dumps(feature_id)
            + b', "geometry":'
            + geometry.encode()
            + b', "properties":'
            + orjson.dumps(model.model_dump())
            + b"}"
        )
        yield feature_bytes
    tail = {
        "numberReturned": count,
        "timeStamp": datetime.datetime.now(datetime.UTC).isoformat(),
    }
    if limit is not None and count == limit:
        query_param = (
            f"&after_id={feature_id}"
            if "?" in request_url
            else f"?after_id={feature_id}"
        )
        next_url = f"{request_url}{query_param}"
        tail["links"] = [
            {"rel": "next", "href": next_url, "type": "application/geo+json"}
        ]
    yield b"]," + orjson.dumps(tail)[1:]  # Close last feature, strip leading '{'


async def patch_feature_geojson(
    collection_id: str, feature_id: str, patch: dict, conn: Connection
):
    target = await get_feature_geojson(collection_id, feature_id, conn)
    for key, value in patch.items():
        if isinstance(target.properties[key], Enum):
            target.properties[key] = type(target.properties[key])(patch.get(key))
        else:
            target.properties[key] = patch.get(key)
    await dao.patch_nongeometry_attributes(target, conn)
    return target


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
