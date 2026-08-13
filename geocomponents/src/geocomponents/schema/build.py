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
    UPSERT_OP,
    WRITE_OPS,
    CollectionPlan,
    ColumnPlan,
    ForeignKeyPlan,
    GeometryColumnPlan,
    IndexPlan,
    SchemaPlan,
    TablePlan,
    internal_function,
)

# Token → SQL expression for top-level scalar server_managed fields.
_SCALAR_SERVER_WRITE: dict[str, str] = {
    "timestamp_iso": "now()",
}


def _feature_property_text_expr(dot_path: str) -> str:
    parts = dot_path.split(".")
    if len(parts) == 1:
        return f"(feature->'properties'->>'{parts[0]}')"

    head, *tail = parts
    expr = f"feature->'properties'->'{head}'"
    for part in tail[:-1]:
        expr = f"({expr}->'{part}')"
    return f"({expr}->>'{tail[-1]}')"


def _standard_columns() -> list[ColumnPlan]:
    return [
        ColumnPlan(
            "id", "uuid", nullable=False, primary_key=True, default="gen_random_uuid()"
        ),
        ColumnPlan("created_at", "timestamptz", nullable=False, default="now()"),
        ColumnPlan("updated_at", "timestamptz", nullable=False, default="now()"),
    ]


def _build_table(schema: str, coll: ResolvedCollection) -> TablePlan:  # noqa: PLR0912
    columns: list[ColumnPlan] = _standard_columns()
    indexes: list[IndexPlan] = []
    upsert_path = coll.upsert_path

    for fld in coll.fields:
        if fld.sql_type == "jsonb":
            # Translate server_managed_paths entries for this field into
            # ColumnPlan injection metadata.  Only consider paths whose first
            # dot-segment matches this field's name.
            strip_keys: list[str] = []
            id_inject_key: str | None = None
            write_inject: list[tuple[str, str]] = []

            for path, rule in coll.server_managed_paths.items():
                parts = path.split(".", 1)
                if len(parts) == 2 and parts[0] == fld.name:  # noqa: PLR2004
                    sub_key = parts[1]
                    if rule == "outward_identifier":
                        if path == upsert_path:
                            continue
                        strip_keys.append(sub_key)
                        id_inject_key = sub_key
                    elif rule == "timestamp_iso":
                        strip_keys.append(sub_key)
                        write_inject.append((sub_key, "now()::text"))

            # The standalone `outward_identifier:` key is stored separately from
            # `server_managed_paths`.  If it targets a sub-field of this JSONB
            # column, apply the same strip-on-write / inject-on-read behaviour.
            if coll.outward_identifier_path is not None:
                oi_parts = coll.outward_identifier_path.split(".", 1)
                if len(oi_parts) == 2 and oi_parts[0] == fld.name:  # noqa: PLR2004
                    sub_key = oi_parts[1]
                    if coll.outward_identifier_path != upsert_path:
                        if sub_key not in strip_keys:
                            strip_keys.append(sub_key)
                        id_inject_key = sub_key

            # Functional indexes for directly indexable sub-fields.
            # SafeIdentifier guarantees no single quotes in key names.
            for sf in fld.sub_fields:
                if sf.indexable:
                    expr = f"(\"{fld.name}\"->>'{sf.name}')"
                    indexes.append(IndexPlan(expr))

            columns.append(
                ColumnPlan(
                    fld.name,
                    fld.sql_type,
                    nullable=not fld.required,
                    strip_keys=tuple(strip_keys),
                    id_inject_key=id_inject_key,
                    write_inject=tuple(write_inject),
                )
            )
        else:
            # Check for single-segment server_managed path matching this field.
            server_write_expr: str | None = None
            if fld.name in coll.server_managed_paths:
                token = coll.server_managed_paths[fld.name]
                if token == "outward_identifier":
                    if coll.outward_identifier_path is None:
                        msg = (
                            f"collection '{coll.name}' uses server_managed outward_identifier "
                            f"for field '{fld.name}' without an outward_identifier path"
                        )
                        raise ValueError(msg)
                    server_write_expr = _feature_property_text_expr(
                        coll.outward_identifier_path
                    )
                else:
                    server_write_expr = _SCALAR_SERVER_WRITE.get(token)
            columns.append(
                ColumnPlan(
                    fld.name,
                    fld.sql_type,
                    nullable=not fld.required,
                    auto_increment=fld.auto_increment,
                    codelist_values=fld.codelist_values,
                    server_write_expr=server_write_expr,
                )
            )
            if fld.indexable:
                indexes.append(IndexPlan(f'"{fld.name}"'))

    foreign_keys: list[ForeignKeyPlan] = []
    for rel in coll.relationships:
        col_name = f"{rel.name}_id"
        columns.append(ColumnPlan(col_name, "uuid", nullable=True))
        foreign_keys.append(
            ForeignKeyPlan(col_name, ref_table=f"{schema}.{rel.target}")
        )

    geometry = GeometryColumnPlan(
        coll.geometry_field,
        coll.geometry_type,
        coll.srid,
        has_z=coll.has_z,
    )
    return TablePlan(
        schema=schema,
        name=coll.name,
        columns=tuple(columns),
        geometry=geometry,
        foreign_keys=tuple(foreign_keys),
        indexes=tuple(indexes),
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
        if coll.supports_upsert:
            ops += (UPSERT_OP,)
        functions = {op: internal_function(schema, coll.name, op) for op in ops}
        collections.append(
            CollectionPlan(
                collection_name=coll.name,
                table=table,
                functions=functions,
                upsert_field=coll.upsert_field,
                upsert_path=coll.upsert_path,
            )
        )
    return SchemaPlan(schema_name=schema, collections=tuple(collections))
