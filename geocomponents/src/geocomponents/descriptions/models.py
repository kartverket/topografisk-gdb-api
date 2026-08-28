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
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

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
    # Nested object stored as JSONB; sub-fields live in FieldDef.fields.
    "object": "jsonb",
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


# Names flowing into generated SQL are validated at parse time so authoring
# errors surface as pydantic ValidationErrors, not cryptic PG syntax failures
# during DDL apply. Domain-facing names like ``FKB-AR5`` will be translated to
# conforming identifiers upstream by the planned descriptor generator; do NOT
# relax this pattern here.
SafeIdentifier = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z_][a-z0-9_]*$", min_length=1, max_length=40),
]


# --------------------------------------------------------------------------
# Raw description documents (validated structure, not data)
# --------------------------------------------------------------------------
class FieldType(BaseModel):
    """A named, reusable attribute type referenced across collections."""

    name: SafeIdentifier
    sql_type: str
    description: str | None = None


class CodeListValue(BaseModel):
    code: str
    label: str | None = None


class CodeList(BaseModel):
    """A shared controlled vocabulary referenced by fields."""

    name: SafeIdentifier
    values: list[CodeListValue] = Field(default_factory=list)


_VALID_SERVER_MANAGED_TOKENS: frozenset[str] = frozenset(
    {"outward_identifier", "timestamp_iso"}
)


class FieldDef(BaseModel):
    """One attribute of a collection.

    Exactly one of ``type`` (builtin token), ``type_ref`` (a ``FieldType``
    name) or ``codelist`` (a ``CodeList`` name) selects the column type.
    For ``type: object``, ``fields`` must be non-empty and defines the
    nested sub-fields (stored as JSONB at arbitrary depth).
    """

    name: SafeIdentifier
    type: str | None = None
    type_ref: str | None = None
    codelist: str | None = None
    required: bool = False
    auto_increment: bool = False
    description: str | None = None
    # Nested sub-fields for type:object columns (stored as JSONB).
    fields: list[FieldDef] = Field(default_factory=list)
    # Documentation-only enum values; not enforced at the DB level.
    enum: list[str] = Field(default_factory=list)
    # When True, the schema builder emits an index for this field.
    indexable: bool = False

    @model_validator(mode="after")
    def _exactly_one_type_source(self):
        if self.type == "object":
            if not self.fields:
                raise ValueError(
                    "field with type='object' must have at least one sub-field "
                    "in 'fields'"
                )
            if self.type_ref is not None or self.codelist is not None:
                raise ValueError(
                    "field with type='object' must not also set type_ref or codelist"
                )
        else:
            n_set = sum(
                x is not None for x in (self.type, self.type_ref, self.codelist)
            )
            if n_set != 1:
                raise ValueError(
                    "field must set exactly one of type / type_ref / codelist "
                    f"(got {n_set})"
                )
        if self.auto_increment and self.type != "integer":
            raise ValueError("auto_increment is only supported for integer fields")
        return self


# Self-referential model requires an explicit rebuild so Pydantic resolves
# the forward reference to FieldDef inside FieldDef.fields.
FieldDef.model_rebuild()


class GeometryDef(BaseModel):
    type: GeometryType = "Point"
    srid: int = 4326
    has_z: bool = False
    required: bool = True


class RelationshipDef(BaseModel):
    """A declared link from a source collection to a target collection.

    ``property`` is property-name on the source feature; ``target`` names
    the collection this property points at. Property names are stored verbatim
    (UML spelling, including uppercase and ø/å); ``target`` must be a
    ``SafeIdentifier`` because it becomes a table reference.
    """

    property: str
    target: SafeIdentifier
    description: str | None = None


class CollectionDef(BaseModel):
    name: SafeIdentifier
    title: str | None = None
    description: str | None = None
    feature_model: FeatureModel = "simple"
    geometry: GeometryDef = Field(default_factory=GeometryDef)
    fields: list[FieldDef] = Field(default_factory=list)
    relationships: list[RelationshipDef] = Field(default_factory=list)
    # Dot-path to the JSONB sub-field whose value is injected from the feature
    # id on read and stripped on write (e.g. "identifikasjon.lokalid").
    outward_identifier: str | None = None
    # Maps dot-paths to server-managed token values.  Allowed tokens:
    # "outward_identifier" — for JSONB targets, inject id::text on read and
    #                         strip on write; for scalar targets, copy the
    #                         referenced outward_identifier value on write.
    # "timestamp_iso"      — inject now()::text on write.
    server_managed: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_collection(self):
        invalid_tokens = {
            v
            for v in self.server_managed.values()
            if v not in _VALID_SERVER_MANAGED_TOKENS
        }
        if invalid_tokens:
            raise ValueError(
                f"server_managed has invalid token(s): {sorted(invalid_tokens)}; "
                f"allowed: {sorted(_VALID_SERVER_MANAGED_TOKENS)}"
            )
        return self


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
    name: SafeIdentifier
    title: str | None = None
    description: str | None = None
    processes: list[str] = Field(default_factory=list)
    collections: list[CollectionDef] = Field(default_factory=list)
    # Named codelists defined within this dataset.  Fields reference them by
    # name via ``codelist: name``; values are used for DB-level validation.
    codelists: list[CodeList] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Resolved, DB-neutral layer (produced by the loader)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class ResolvedField:
    name: str
    sql_type: str
    required: bool = False
    codelist: str | None = None  # kept for future DB-side enforcement
    auto_increment: bool = False
    # Non-empty for type:object fields; contains the resolved sub-fields.
    sub_fields: tuple[ResolvedField, ...] = field(default_factory=tuple)
    # Documentation-only enum values (not DB-enforced).
    enum: tuple[str, ...] = field(default_factory=tuple)
    # True when the schema builder should emit an index for this field.
    indexable: bool = False
    # Actual code values from the referenced CodeList (used for DB validation).
    codelist_values: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResolvedRelationship:
    property: str  # property-rolename on source
    target: str  # target collection name


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
    upsert_field: str | None = None
    upsert_path: str | None = None
    has_z: bool = False
    geometry_required: bool = True
    # Dot-path to the outward-identifier sub-field (e.g. "identifikasjon.lokalid").
    outward_identifier_path: str | None = None
    # Server-managed dot-paths -> token values (mirrors CollectionDef.server_managed).
    server_managed_paths: dict[str, str] = field(default_factory=dict)

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

    @property
    def supports_upsert(self) -> bool:
        return self.supports_crud and self.upsert_field is not None


@dataclass(frozen=True)
class ResolvedDataset:
    name: str
    title: str
    description: str
    processes: tuple[str, ...] = field(default_factory=tuple)
    collections: tuple[ResolvedCollection, ...] = field(default_factory=tuple)
