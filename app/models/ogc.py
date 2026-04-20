from typing import Optional, List, Union

from pydantic import BaseModel, ConfigDict, Field
from geojson_pydantic import Point, MultiPoint, LineString, MultiLineString, Polygon, MultiPolygon, GeometryCollection


Geometry = Union[
    Point,
    MultiPoint,
    LineString,
    MultiLineString,
    Polygon,
    MultiPolygon,
    GeometryCollection
]

class OGCBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # accept both Python name and alias
        alias_generator=None,  # explicit aliases only — no auto-camel-case
    )

class Link(OGCBase):
    href: str
    rel: Optional[str] = None
    type: Optional[str] = None
    hreflang: Optional[str] = None
    title: Optional[str] = None
    length: Optional[int] = None

class LandingPage(OGCBase):
    title: Optional[str] = None
    description: Optional[str] = None
    links: List[Link]

class Conformance(OGCBase):
    conforms_to: List[str] = Field(alias="conformsTo")

class SpatialExtent(OGCBase):
    bbox: Optional[List[List[float]]] = None
    crs: Optional[str] = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

class TemporalExtent(OGCBase):
    interval: Optional[List[List[Optional[str]]]] = None
    trs: Optional[str] = None

class Extent(OGCBase):
    spatial: Optional[SpatialExtent] = None
    temporal: Optional[TemporalExtent] = None

class CollectionMetadata(OGCBase):
    title: str
    description: str

class Collection(OGCBase):
    id : str
    title: Optional[str] = None
    description: Optional[str] = None
    links: List[Link]
    extent: Optional[Extent] = None
    item_type: Optional[str] = Field(None, alias="itemType")
    crs: List[str] = ["EPSG:5973"]

class Collections(OGCBase):
    links: List[Link]
    collections: List[Collection]

class FeatureGeoJSON(OGCBase):
    id: Optional[str | int] = None
    type: str = "Feature"
    links: Optional[List[Link]] = None
    geometry: Geometry
    properties: object

class FeatureCollectionGeoJSON(OGCBase):
    type: str = "FeatureCollection"
    links: Optional[List[Link]] = None
    time_stamp: Optional[str] = Field(None, alias="timeStamp")
    number_matched: Optional[int] = Field(None, alias="numberMatched")
    number_returned: Optional[int] = Field(None, alias="numberReturned")
    features: List[FeatureGeoJSON]
