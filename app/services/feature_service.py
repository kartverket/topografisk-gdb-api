import datetime
from enum import Enum

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


async def get_feature_collection(
    collection_id: str,
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
    rows = await dao.get_feature_collection(
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
        sep = "&" if "?" in request_url else "?"
        body["links"] = [
            {
                "rel": "next",
                "href": f"{request_url}{sep}after_id={last_id}",
                "type": "application/geo+json",
            }
        ]
    return orjson.dumps(body)


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
