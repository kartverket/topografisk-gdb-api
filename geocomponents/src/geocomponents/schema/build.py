"""Turn a resolved description into a DB-neutral ``SchemaPlan``.

Mapping rules (the heart of "description owns the names"):

* dataset            -> PostgreSQL schema (named after the dataset)
* collection         -> table inside that schema
* every collection   -> id (uuid PK) + geometry + created_at/updated_at columns
* commons + own fields -> attribute columns
* relationship       -> ``<name>_id`` uuid foreign key to the target table
* each collection    -> one function name per operation (``<table>_<op>``)
"""

from __future__ import annotations

from geocomponents.descriptions.models import ResolvedCollection, ResolvedDataset
from geocomponents.schema.plan import (
    READ_OPS,
    WRITE_OPS,
    CollectionPlan,
    ColumnPlan,
    ForeignKeyPlan,
    GeometryColumnPlan,
    SchemaPlan,
    TablePlan,
    internal_function,
)


def _standard_columns() -> list[ColumnPlan]:
    return [
        ColumnPlan(
            "id", "uuid", nullable=False, primary_key=True, default="gen_random_uuid()"
        ),
        ColumnPlan("created_at", "timestamptz", nullable=False, default="now()"),
        ColumnPlan("updated_at", "timestamptz", nullable=False, default="now()"),
    ]


def _build_table(schema: str, coll: ResolvedCollection) -> TablePlan:
    columns: list[ColumnPlan] = _standard_columns()

    for fld in coll.fields:
        columns.append(
            ColumnPlan(
                fld.name,
                fld.sql_type,
                nullable=not fld.required,
                auto_increment=fld.auto_increment,
            )
        )

    foreign_keys: list[ForeignKeyPlan] = []
    for rel in coll.relationships:
        col_name = f"{rel.name}_id"
        columns.append(ColumnPlan(col_name, "uuid", nullable=True))
        foreign_keys.append(
            ForeignKeyPlan(col_name, ref_table=f"{schema}.{rel.target}")
        )

    geometry = GeometryColumnPlan(coll.geometry_field, coll.geometry_type, coll.srid)
    return TablePlan(
        schema=schema,
        name=coll.name,
        columns=tuple(columns),
        geometry=geometry,
        foreign_keys=tuple(foreign_keys),
    )


def build_schema_plan(dataset: ResolvedDataset) -> SchemaPlan:
    """Turn a resolved dataset into a ``SchemaPlan`` -- the tables, columns,
    geometries, foreign keys, and function names it needs.
    """
    schema = dataset.name
    collections: list[CollectionPlan] = []
    for coll in dataset.collections:
        table = _build_table(schema, coll)
        # Reads for every collection; writes only for simple-feature collections.
        ops = READ_OPS + WRITE_OPS if coll.supports_crud else READ_OPS
        functions = {op: internal_function(schema, coll.name, op) for op in ops}
        collections.append(
            CollectionPlan(
                collection_name=coll.name,
                table=table,
                functions=functions,
            )
        )
    return SchemaPlan(schema_name=schema, collections=tuple(collections))
