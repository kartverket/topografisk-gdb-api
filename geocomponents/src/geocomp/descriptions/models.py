"""Meta-schema for dataset descriptions.

Two layers live here:

* **Raw** Pydantic models (``Commons``, ``Dataset`` ...) that validate the
  *shape of a description document* — names present, field types known, refs
  resolvable. They do **not** validate feature data.
* **Resolved** dataclasses (``ResolvedDataset`` ...) produced by the loader
  after merging commons, inheriting the base schema, and turning type tokens
  into concrete SQL types. Everything downstream (schema generation, the API
  adapter) reads the resolved layer, so it never deals with commons indirection.

The resolved layer is intentionally DB-neutral: ``sql_type`` happens to be a
PostgreSQL type here, but the concept (a column with a type) is generic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Builtin scalar types -> PostgreSQL column types. FieldType.sql_type overrides.
# --------------------------------------------------------------------------
BUILTIN_SQL_TYPES: dict[str, str] = {
    "string": "text",
    "integer": "integer",
    "number": "double precision",
    "boolean": "boolean",
    "date": "date",
    "timestamp": "timestamptz",
    "uuid": "uuid",
}

GeometryType = Literal[
    "Point",
    "MultiPoint",
    "LineString",
    "MultiLineString",
    "Polygon",
    "MultiPolygon",
    "GeometryCollection",
]

# A collection's feature model decides which operations are generated/exposed:
#  - "simple"   : independent features -> OGC Features + Part 4 CRUD.
#  - "topology" : features share geometry -> reads only for now. Per-feature CRUD
#                 is unsafe here and will arrive later via processes + the OGC
#                 Features Part 11 (Transactions) draft.
FeatureModel = Literal["simple", "topology"]


# --------------------------------------------------------------------------
# Raw description documents (validated structure, not data)
# --------------------------------------------------------------------------
class FieldType(BaseModel):
    """A named, reusable attribute type referenced across collections."""

    name: str
    sql_type: str
    description: str | None = None


class CodeListValue(BaseModel):
    code: str
    label: str | None = None


class CodeList(BaseModel):
    """A shared controlled vocabulary referenced by fields."""

    name: str
    values: list[CodeListValue] = Field(default_factory=list)


class FieldDef(BaseModel):
    """One attribute of a collection.

    Exactly one of ``type`` (builtin token), ``type_ref`` (a ``FieldType``
    name) or ``codelist`` (a ``CodeList`` name) selects the column type.
    """

    name: str
    type: str | None = None
    type_ref: str | None = None
    codelist: str | None = None
    required: bool = False
    description: str | None = None


class GeometryDef(BaseModel):
    type: GeometryType = "Point"
    srid: int = 4326


class RelationshipDef(BaseModel):
    """A foreign-key-like link to another collection in the same dataset.

    Generates a ``<name>_id`` column referencing the target's ``id``.
    """

    name: str
    target: str
    description: str | None = None


class CollectionDef(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    feature_model: FeatureModel = "simple"
    geometry: GeometryDef = Field(default_factory=GeometryDef)
    fields: list[FieldDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)


class Commons(BaseModel):
    """Shared definitions inherited by every collection in every dataset.

    ``base_fields`` are extra attributes every collection gets (on top of the
    always-present id/geometry/audit columns). ``field_types`` and
    ``code_lists`` are the reusable vocabularies fields may reference.
    """

    base_fields: list[FieldDef] = Field(default_factory=list)
    field_types: list[FieldType] = Field(default_factory=list)
    code_lists: list[CodeList] = Field(default_factory=list)


class DatasetDef(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    processes: list[str] = Field(default_factory=list)
    collections: list[CollectionDef] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Resolved, DB-neutral layer (produced by the loader)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedField:
    name: str
    sql_type: str
    required: bool = False
    codelist: str | None = None  # kept for future DB-side enforcement


@dataclass(frozen=True)
class ResolvedRelationship:
    name: str           # column base name; column is <name>_id
    target: str         # target collection (table) name


@dataclass(frozen=True)
class ResolvedCollection:
    name: str
    title: str
    description: str
    feature_model: str
    geometry_type: str
    srid: int
    fields: tuple[ResolvedField, ...]
    relationships: tuple[ResolvedRelationship, ...]

    @property
    def id_field(self) -> str:
        return "id"

    @property
    def geometry_field(self) -> str:
        return "geometry"

    @property
    def supports_crud(self) -> bool:
        """Simple features get per-feature Part 4 CRUD; topology does not (yet)."""
        return self.feature_model == "simple"


@dataclass(frozen=True)
class ResolvedDataset:
    name: str
    title: str
    description: str
    processes: tuple[str, ...] = field(default_factory=tuple)
    collections: tuple[ResolvedCollection, ...] = field(default_factory=tuple)
