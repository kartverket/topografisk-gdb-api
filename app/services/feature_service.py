import datetime
from enum import Enum
from typing import AsyncGenerator, Tuple

import orjson
from psycopg import Connection

from app.db.fkb_ar5_dao import FKBAR5DAO
from app.models.fkb_felles import FKBFelles
from app.models.ogc import FeatureGeoJSON
from app.postgis_backend import PostGISBackend


class Accessor(Enum):
    GET_ONE = 1
    GET_LIST = 2
    CREATE = 3
    PATCH = 4
    DELETE = 5


# TODO: remove nonexisting keys such as Accessor.DELETE?
# In that way we fail with a bang (KeyError) instead of
# some None type error somewhere?
DB_ACCESSORS = {
    "arealressursflate": {
        Accessor.GET_ONE: FKBAR5DAO.get_feature,
        Accessor.GET_LIST: FKBAR5DAO.get_feature_collection,
        Accessor.CREATE: FKBAR5DAO.create_arealressursflate,
        Accessor.PATCH: FKBAR5DAO.patch_arealressursflate,
        Accessor.DELETE: None,
    },
    "arealressursgrense": {
        Accessor.GET_ONE: FKBAR5DAO.get_feature,
        Accessor.GET_LIST: FKBAR5DAO.get_feature_collection,
        Accessor.CREATE: FKBAR5DAO.create_arealressursgrense,
        Accessor.PATCH: None,
        Accessor.DELETE: None,
    },
    "jernbaneplattformkant": {
        Accessor.GET_ONE: PostGISBackend.get_jernbaneplattformkant,
        Accessor.GET_LIST: PostGISBackend.get_all_jernbaneplattformkant,
        Accessor.CREATE: PostGISBackend.create_jernbaneplattformkant,
        Accessor.PATCH: None,
        Accessor.DELETE: None,
    },
    "spormidt": {
        Accessor.GET_ONE: PostGISBackend.get_spormidt,
        Accessor.GET_LIST: PostGISBackend.get_all_spormidt,
        Accessor.CREATE: PostGISBackend.create_spormidt,
        Accessor.PATCH: None,
        Accessor.DELETE: None,
    },
}


def get_accessor(collection_id: str, accessor_type: Accessor):
    return DB_ACCESSORS[collection_id][accessor_type]


def to_featuregeojson(featuredata: Tuple[FKBFelles, str]):
    return FeatureGeoJSON(
        id=featuredata[0].identifikasjon.lokal_id,
        geometry=orjson.loads(featuredata[1]),
        properties=featuredata[0],
    )


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> FeatureGeoJSON:
    """Fetch a single feature and return it as a plain GeoJSON dict.

    Sketch function that fits the signature in FeatureService.
    """
    accessor = get_accessor(collection_id, Accessor.GET_ONE)
    if collection_id in {"arealressursgrense", "arealressursflate"}:
        model, geometry = await accessor(
            conn=conn, collection_id=collection_id, feature_id=feature_id
        )
    else:
        model, geometry = await accessor(collection_id, Accessor.GET_ONE)(
            feature_id, conn
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
    generator = get_accessor(collection_id, Accessor.GET_LIST)(
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
    await get_accessor(collection_id, Accessor.PATCH)(target, conn)
    return target


async def create_feature_geojson(
    collection_id: str, feature: FeatureGeoJSON, conn: Connection
):
    created_id = await get_accessor(collection_id, Accessor.CREATE)(
        feature.properties, feature.geometry, conn
    )
    return created_id
