from typing import List

from fastapi import APIRouter, HTTPException, Request, Query, Depends
from fastapi.responses import JSONResponse
from psycopg import Connection

from app.models.ogc import (
    Extent,
    Link,
    Collections,
    Collection,
    FeatureCollectionGeoJSON,
    FeatureGeoJSON,
    LandingPage,
    Conformance,
    CollectionMetadata
)
from app.models.exceptions import FeatureNotFoundError
from app.services.feature_service import create_feature_service
from app.database_manager import get_db_conn

router = APIRouter(tags=["OGC API Features - FKB Bane"])

COLLECTIONS = [
    "jernbaneplattformkant",
    "spormidt",
    "arealressursflate",
]

COLLECTION_METADATA = {
    "jernbaneplattformkant": CollectionMetadata(
        title="Jernbaneplattformkant",
        description="Inneholder jernbaneplattformkanter"
    ),
    "spormidt": CollectionMetadata(
        title="Spormidt",
        description="Inneholder jernbanespor"
    ),
    "arealressursflate": CollectionMetadata(
        title="Arealressurs flate",
        description="Inneholder arealressurs flate"
    )
}

def collection_from_id(collection_id: str, request: Request):
    metadata = COLLECTION_METADATA[collection_id]
    return Collection(
        id=collection_id,
        title=metadata.title,
        description=metadata.description,
        extent=Extent(),
        links=[
            Link(
                href=f"{request.base_url}collections/{collection_id}",
                rel="self",
                type="application/json",
                title=f"{metadata.title} collection",
            ),
            Link(
                href=f"{request.base_url}collections/{collection_id}/items",
                rel="items",
                type="application/geo+json",
                title=f"{metadata.title} features",
            ),
        ]
    )

@router.get("/", response_model=LandingPage, status_code=200)
async def get_landing(request: Request):
    return LandingPage(
        title="FKB Bane",
        description="ForvaltningsAPI for FKB Bane som samsvarer med OGC-standarder.",
        links=[
            Link(
                href=f"{request.url}",
                rel="self",
                type="application/json",
                title="this document"
            ),
            Link(
                href=f"{request.base_url}docs",
                rel="service-desc",
                title="API-definisjonen"
            ),
            Link(
                href=f"{request.base_url}conformance",
                rel="conformance",
                type="application/json",
                title="OGC API conformance-klasser som implementeres av denne serveren"
            ),
            Link(
                href=f"{request.base_url}collections",
                rel="data",
                type="application/json",
                title="Informasjon om feature collections"
            )
        ]
    )

@router.get("/conformance", response_model=Conformance, status_code=200)
async def get_conformance():
    return Conformance(
        conforms_to=[
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/req/core",
            "http://www.opengis.net/spec/ogcapi-features-1/1.0/req/geojson"
        ]
    )

@router.get("/collections", response_model=Collections, status_code=200) #Oversikt over alle datasett API-et vårt tilbyr
async def get_collections(request: Request):
    return Collections(
        collections=map(lambda id: collection_from_id(id, request), COLLECTIONS),
        links=[
            Link(
                href=f"{request.base_url}collections",
                rel="self",
                type="application/json",
                title="Collections",
            )
        ],
    )

@router.get("/collections/{collection_id}", response_model=Collection, status_code=200) #Metadata om datasett, men ikke selve dataen
async def get_collection(collection_id: str, request: Request):
    if collection_id not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    return collection_from_id(collection_id, request)

@router.get("/collections/{collection_id}/items", response_model=FeatureCollectionGeoJSON, status_code=200) #Hent flere features
async def get_features(
    collection_id: str,
    bbox: List[float] = Query(
        default=[]
    ),
    datetime: str | None = Query(
        default=None
    ),
    limit: int = Query(
        default=10
    ),
    conn: Connection = Depends(get_db_conn)
):
    if collection_id not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")

    feature_service = create_feature_service(collection_id)
    return await feature_service.get_features(conn)

@router.get("/collections/{collection_id}/items/{feature_id}", response_model=FeatureGeoJSON, status_code=200) #Hent en feature
async def get_feature(collection_id: str, feature_id: str, conn: Connection = Depends(get_db_conn)):
    if collection_id not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    feature_service = create_feature_service(collection_id)
    try:
        return await feature_service.get_feature(feature_id, conn)
    except FeatureNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/collections/{collection_id}/items", response_model=str, status_code=201) # lag en ny feature
async def create_feature(
    collection_id: str,
    feature: FeatureGeoJSON,
    request: Request,
    conn: Connection = Depends(get_db_conn)
):
    if collection_id not in COLLECTIONS:
        raise HTTPException(status_code=404, detail="Collection not found")
    
    feature_service = create_feature_service(collection_id)
    created_id = await feature_service.create_feature(feature, conn)
    headers = {"Location": f"{request.base_url}collections/{collection_id}/items/{created_id}"}
    return JSONResponse(content=created_id, headers=headers)

@router.patch("/collections/{collection_id}/items/{feature_id}", response_model=FeatureGeoJSON, status_code=200)
async def update_feature(collection_id: str, feature: FeatureGeoJSON, conn: Connection = Depends(get_db_conn)):
    raise NotImplementedError()

@router.delete("/collections/{collection_id}/items/{feature_id}", status_code=200)
async def delete_feature(collection_id: str, feature: FeatureGeoJSON, conn: Connection = Depends(get_db_conn)):
    raise NotImplementedError()
