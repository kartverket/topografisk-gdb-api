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
UPSERT_OP = "upsert"

# The API only ever calls this fixed dispatch layer, with OGC identifiers
# (dataset, collection) as *arguments* — never a physical table or per-collection
# function name. The dispatcher routes (by convention) to the internal,
# generated per-collection functions. This keeps the description + OGC as the
# contract and lets the physical layout change underneath without touching the API.
#
# The schema name is deliberately *product-neutral* (``ogc``, the standard this
# surface implements) rather than the package name, so the wire contract is
# decoupled from any future rebrand of the tool. The ``feature_`` prefix is kept
# because bare verbs like ``create`` collide with SQL reserved words.
DISPATCH_SCHEMA = "ogc"


def dispatch_function(operation: str) -> str:
    """Public, stable entrypoint the API calls, e.g. ``ogc.feature_items``."""
    return f"{DISPATCH_SCHEMA}.feature_{operation}"


def internal_function(schema: str, collection: str, operation: str) -> str:
    """Generated, private per-collection implementation the dispatcher routes to.

    Naming convention (``<schema>._<collection>_<op>``) is the contract between
    the dispatcher and the generator — both internal to the DB seam.
    """
    return f"{schema}._{collection}_{operation}"


def upsert_sql_expression(path: str) -> str:
    """Render one upsert key path as a SQL conflict/index expression."""
    parts = path.split(".")
    if len(parts) == 1:
        return f'"{parts[0]}"'
    head, *tail = parts
    return f"(\"{head}\" #>> '{{{','.join(tail)}}}')"


@dataclass(frozen=True)
class IndexPlan:
    """One index to emit after the table DDL."""

    expression: str  # column name or functional expression, without outer parens
    unique: bool = False
    method: str = "btree"


@dataclass(frozen=True)
class ColumnPlan:
    name: str
    sql_type: str
    nullable: bool = True
    primary_key: bool = False
    default: str | None = None
    auto_increment: bool = False
    # JSONB-only: keys stripped from incoming feature properties before storing.
    strip_keys: tuple[str, ...] = ()
    # JSONB-only: key injected as id::text in the GeoJSON read response.
    id_inject_key: str | None = None
    # JSONB-only: (key, sql_expr) pairs injected when writing to the DB.
    write_inject: tuple[tuple[str, str], ...] = ()
    # Permitted code values for DB-level validation (empty = no validation).
    codelist_values: tuple[str, ...] = ()
    # Scalar server-managed: SQL expression substituted for client input on write.
    # When set, the column is excluded from the writable set entirely.
    server_write_expr: str | None = None


@dataclass(frozen=True)
class GeometryColumnPlan:
    name: str
    geometry_type: str
    srid: int
    has_z: bool = False

    @property
    def postgis_type(self) -> str:
        """PostGIS typmod geometry type (``LineStringZ`` when height is enabled)."""
        if self.has_z and not self.geometry_type.endswith(("Z", "M")):
            return f"{self.geometry_type}Z"
        return self.geometry_type


@dataclass(frozen=True)
class ForeignKeyPlan:
    column: str
    ref_table: str  # schema-qualified
    ref_column: str = "id"


@dataclass(frozen=True)
class TablePlan:
    schema: str
    name: str
    columns: tuple[ColumnPlan, ...]
    geometry: GeometryColumnPlan
    foreign_keys: tuple[ForeignKeyPlan, ...] = ()
    indexes: tuple[IndexPlan, ...] = ()

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
    functions: dict[str, str]  # operation -> internal function name (private)
    upsert_field: str | None = None
    upsert_path: str | None = None

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
