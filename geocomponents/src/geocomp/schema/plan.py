"""DB-neutral schema plan.

A ``SchemaPlan`` is the intermediate between a description and a concrete
database. It says *what* must exist (a namespace, tables, columns, a geometry
column, foreign keys, and the set of read/CRUD operations) without saying *how*
any particular database realises it. The PostGIS adapter (``postgis.py`` +
``functions.py``) is one consumer; a future migration emitter or a different
database backend would be another, reusing this same plan.
"""

from __future__ import annotations

from dataclasses import dataclass

# Operations split by capability: reads exist for every collection; writes
# (Part 4 CRUD) are generated only for "simple" collections.
READ_OPS = ("items", "item")
WRITE_OPS = ("create", "replace", "update", "delete")
OPERATIONS = READ_OPS + WRITE_OPS

# The API only ever calls this fixed dispatch layer, with OGC identifiers
# (dataset, collection) as *arguments* — never a physical table or per-collection
# function name. The dispatcher routes (by convention) to the internal,
# generated per-collection functions. This keeps the description + OGC as the
# contract and lets the physical layout change underneath without touching the API.
#
# The prefix is a neutral namespace marker (these operate on GeoJSON features),
# not a claim of OGC-specificity; bare verbs like ``create`` collide with SQL
# reserved words, so we keep ``feature_``.
DISPATCH_SCHEMA = "geocomp"


def dispatch_function(operation: str) -> str:
    """Public, stable entrypoint the API calls, e.g. ``geocomp.feature_items``."""
    return f"{DISPATCH_SCHEMA}.feature_{operation}"


def internal_function(schema: str, collection: str, operation: str) -> str:
    """Generated, private per-collection implementation the dispatcher routes to.

    Naming convention (``<schema>._<collection>_<op>``) is the contract between
    the dispatcher and the generator — both internal to the DB seam.
    """
    return f"{schema}._{collection}_{operation}"


@dataclass(frozen=True)
class ColumnPlan:
    name: str
    sql_type: str
    nullable: bool = True
    primary_key: bool = False
    default: str | None = None


@dataclass(frozen=True)
class GeometryColumnPlan:
    name: str
    geometry_type: str
    srid: int


@dataclass(frozen=True)
class ForeignKeyPlan:
    column: str
    ref_table: str   # schema-qualified
    ref_column: str = "id"


@dataclass(frozen=True)
class TablePlan:
    schema: str
    name: str
    columns: tuple[ColumnPlan, ...]
    geometry: GeometryColumnPlan
    foreign_keys: tuple[ForeignKeyPlan, ...] = ()

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.name}"

    @property
    def id_column(self) -> str:
        for col in self.columns:
            if col.primary_key:
                return col.name
        return "id"

    @property
    def property_columns(self) -> tuple[ColumnPlan, ...]:
        """Columns surfaced as GeoJSON ``properties`` (everything but the id)."""
        return tuple(c for c in self.columns if not c.primary_key)


@dataclass(frozen=True)
class CollectionPlan:
    collection_name: str
    table: TablePlan
    functions: dict[str, str]   # operation -> internal function name (private)

    @property
    def id_field(self) -> str:
        return self.table.id_column

    @property
    def geometry_field(self) -> str:
        return self.table.geometry.name


@dataclass(frozen=True)
class SchemaPlan:
    """One dataset's plan: a PostgreSQL schema holding one table per collection."""

    schema_name: str
    collections: tuple[CollectionPlan, ...]
