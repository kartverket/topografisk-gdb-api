import datetime
from enum import Enum
from typing import AsyncGenerator, Tuple

import orjson
from fastapi import Request
from psycopg import Connection

from app.db.fkb_ar5_dao import FKBAR5DAO
from app.models.fkb_felles import FKBFelles
from app.models.ogc import FeatureCollectionGeoJSON, FeatureGeoJSON
from app.postgis_backend import PostGISBackend


class Accessor(Enum):
    GET_ONE = 1
    GET_LIST = 2
    CREATE = 3
    PATCH = 4
    DELETE = 5


def get_accessor(collection_id: str, type: Accessor):
    return {
        "arealressursflate": {
            Accessor.GET_ONE: FKBAR5DAO.get_arealressursflate,
            Accessor.GET_LIST: FKBAR5DAO.get_all_arealressursflate,
            Accessor.CREATE: FKBAR5DAO.create_arealressursflate,
            Accessor.PATCH: FKBAR5DAO.patch_arealressursflate,
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
    }[collection_id][type]


def get_one_accessor(collection_id: str):
    return get_accessor(collection_id, Accessor.GET_ONE)


def get_list_accessor(collection_id: str):
    return get_accessor(collection_id, Accessor.GET_LIST)


def get_create_accesor(collection_id: str):
    return get_accessor(collection_id, Accessor.CREATE)


def get_patch_accessor(collection_id: str):
    return get_accessor(collection_id, Accessor.PATCH)


def get_delete_accessor(collection_id: str):
    return get_accessor(collection_id, Accessor.DELETE)


def to_featuregeojson(featuredata: Tuple[FKBFelles, str]):
    return FeatureGeoJSON(
        id=featuredata[0].identifikasjon.lokal_id,
        geometry=orjson.loads(featuredata[1]),
        properties=featuredata[0],
    )


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> dict:
    """Fetch a single feature and return it as a plain GeoJSON dict.

    Sketch function that fits the signature in FeatureService.
    """
    model, geometry = await get_one_accessor(collection_id)(feature_id, conn)
    return FeatureGeoJSON(
        id=model.identifikasjon.lokal_id,
        geometry=orjson.loads(geometry),
        properties=model.model_dump(),
    )


async def get_feature_collection(collection_id: str, conn: Connection):
    features = await get_list_accessor(collection_id)(conn)
    return FeatureCollectionGeoJSON(features=list(map(to_featuregeojson, features)))


async def stream_feature_collection(
    collection_id: str,
    limit: int | None,
    after_id: str | None,
    conn: Connection,
    request: Request,
) -> AsyncGenerator[bytes, None]:
    """Stream a GeoJSON FeatureCollection as bytes, one feature at a time.

    The closing object includes numberReturned, timeStamp, and a rel:next link
    when the returned page is full.
    """
    # TODO: Implement other features, include type hinting
    generator = get_list_accessor(collection_id)(conn, limit, after_id)
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
        next_url = str(request.url.include_query_params(after_id=feature_id))
        tail["links"] = [
            {"rel": "next", "href": next_url, "type": "application/geo+json"}
        ]
    yield b"]," + orjson.dumps(tail)[1:]  # Close last feature, strip leading '{'


async def patch_feature_geojson(
    collection_id: str, feature_id: str, patch: dict, conn: Connection
):
    target = await get_feature_geojson(collection_id, feature_id, conn)
    for key, value in patch.items():
        if isinstance(target["properties"][key], Enum):
            target["properties"][key] = type(target["properties"][key])(patch.get(key))
        else:
            target["properties"][key] = patch.get(key)
    await get_patch_accessor(collection_id)(target, conn)
    return target


async def create_feature_geojson(
    collection_id: str, feature: FeatureGeoJSON, conn: Connection
):
    created_id = await get_create_accesor(collection_id)(
        feature.properties, feature.geometry, conn
    )
    return created_id
