import datetime
from typing import AsyncGenerator, Awaitable, Callable, List, Tuple
import enum

import orjson
from fastapi import Request
from psycopg import Connection

from app.db.fkb_ar5_dao import FKBAR5DAO
from app.models.fkb_felles import FKBFelles
from app.models.ogc import FeatureCollectionGeoJSON, FeatureGeoJSON
from app.postgis_backend import PostGISBackend


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
    generator = {
        "arealressursflate": FKBAR5DAO.get_all_arealressursflate,
    }[collection_id](conn, limit, after_id)
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


async def get_feature_geojson(
    collection_id: str, feature_id: str, conn: Connection
) -> dict:
    """Fetch a single feature and return it as a plain GeoJSON dict.

    Sketch function that fits the signature in FeatureService.
    """
    model, geometry = await {"arealressursflate": FKBAR5DAO.get_arealressursflate}[
        collection_id
    ](conn, feature_id)
    return {
        "type": "Feature",
        "id": model.identifikasjon.lokal_id,
        "geometry": orjson.loads(geometry),
        "properties": model.model_dump(),
    }

async def patch_feature_geojson(collection_id: str, feature_id: str, patch: dict, conn: Connection):
    target = await get_feature_geojson(collection_id, feature_id, conn)
    for key, value in patch.items():
        if isinstance(target["properties"][key], enum.Enum):
            target["properties"][key] = type(target["properties"][key])(patch.get(key))
        else:
            target["properties"][key] = patch.get(key)
    await FKBAR5DAO.patch_arealressursflate(target, conn) #TODO: Generalize, jira: TT-39
    return target


class FeatureService:
    def __init__(self, get_one, get_all, create):
        self.get_one: Callable[[str, Connection], Awaitable[Tuple[FKBFelles, dict]]] = (
            get_one
        )
        self.get_all: Callable[
            [Connection], Awaitable[List[Tuple[FKBFelles, dict]]]
        ] = get_all
        self.create = create

    def to_featuregeojson(self, featuredata: Tuple[FKBFelles, str]):
        return FeatureGeoJSON(
            id=featuredata[0].identifikasjon.lokal_id,
            geometry=featuredata[1],
            properties=featuredata[0],
        )

    async def get_feature(self, feature_id: str, conn: Connection) -> FeatureGeoJSON:
        properties, geometry = await self.get_one(feature_id, conn)
        return FeatureGeoJSON(
            id=properties.identifikasjon.lokal_id,
            geometry=geometry,
            properties=properties,
        )

    async def get_features(self, conn: Connection) -> FeatureCollectionGeoJSON:
        features = await self.get_all(conn)
        return FeatureCollectionGeoJSON(
            features=list(map(self.to_featuregeojson, features))
        )

    async def create_feature(self, feature: FeatureGeoJSON, conn: Connection):
        print(feature.geometry)
        created_id = await self.create(feature.properties, feature.geometry, conn)
        return created_id


def create_feature_service(collection_id: str):
    functions = {
        "jernbaneplattformkant": {
            "get_one": PostGISBackend.get_jernbaneplattformkant,
            "get_all": PostGISBackend.get_all_jernbaneplattformkant,
            "create": PostGISBackend.create_jernbaneplattformkant,
        },
        "spormidt": {
            "get_one": PostGISBackend.get_spormidt,
            "get_all": PostGISBackend.get_all_spormidt,
            "create": PostGISBackend.create_sportmidt,
        },
        "arealressursflate": {
            "get_one": FKBAR5DAO.get_arealressursflate,
            "get_all": FKBAR5DAO.get_all_arealressursflate,
            "create": FKBAR5DAO.create_arealressursflate,
        },
    }[collection_id]

    return FeatureService(**functions)
