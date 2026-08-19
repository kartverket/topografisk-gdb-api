"""Generate + apply the database functions.

Two layers, mirroring the DB/API contract decision:

* **Dispatch layer** (``ogc.feature_*``) — a *fixed*, generic set of functions
  the API calls with OGC identifiers ``(dataset, collection)`` as arguments. It
  is written once, lists no datasets, and routes by naming convention to the
  internal functions via dynamic SQL. **This is the only thing the API names.**
* **Internal functions** (``<dataset>._<collection>_<op>``) — generated per
  collection from the description. They do the actual reading/writing and shape
  feature content to/from GeoJSON. Their names are a DB-internal detail and
  never reach the API.

Feature shaping lives here; OGC hypermedia links / paging envelopes do not
(those depend on the API mount path and are added by pygeoapi).
"""
# ruff: noqa: S608 - This module *generates* SQL DDL; every interpolated value is
# an identifier from the SchemaPlan (schema/table/column/function names + SRID),
# derived from the validated dataset descriptions. Not subject to SQL-injection

from __future__ import annotations

from pathlib import Path

import psycopg

from geocomponents.schema.plan import (
    DISPATCH_SCHEMA,
    CollectionPlan,
    ColumnPlan,
    SchemaPlan,
    TablePlan,
    upsert_sql_expression,
)

# Audit columns are server-managed; never written from incoming features.
_AUDIT = ("created_at", "updated_at")
_SCHEMA_DIR = Path(__file__).resolve().parent


def _quote_key(name: str) -> str:
    """Escape single quotes so ``name`` can be embedded in a SQL literal.

    Defense-in-depth: names are already restricted by the loader's
    ``SafeIdentifier``, but hand-built plans (e.g. tests) can bypass that.
    """
    return name.replace("'", "''")


# ==========================================================================
# Dispatch layer (fixed; generated once, independent of any dataset)
# ==========================================================================
def topogdb_statements() -> list[str]:
    """The fixed PostGIS helper objects under ``topogdb`` applied once per DB."""
    return [(_SCHEMA_DIR / "topogdb_functions.sql").read_text(encoding="utf-8")]


def apply_topogdb(conn: psycopg.Connection) -> None:
    """Create the fixed ``topogdb`` schema objects used by dataset functions."""
    conn.execute("drop schema if exists topogdb cascade")
    for stmt in topogdb_statements():
        conn.execute(stmt)
    conn.commit()


def dispatch_statements() -> list[str]:
    """The stable ``ogc.feature_*`` entrypoints the API calls.

    Each routes to ``<dataset>._<collection>_<op>`` by convention using dynamic
    SQL, so adding a dataset never requires changing the dispatcher.
    """

    s = DISPATCH_SCHEMA
    return [
        f"create schema if not exists {s}",
        f"""\
create or replace function {s}.feature_items(
    dataset text, collection text,
    bbox float8[] default null, lim int default 10, off int default 0,
    with_matched boolean default true)
returns jsonb language plpgsql stable as $disp$
declare result jsonb;
begin
  execute format('select %I.%I($1, $2, $3, $4)', dataset, '_' || collection || '_items')
    into result using bbox, lim, off, with_matched;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_item(dataset text, collection text, fid uuid)
returns jsonb language plpgsql stable as $disp$
declare result jsonb;
begin
  execute format('select %I.%I($1)', dataset, '_' || collection || '_item')
    into result using fid;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_create(dataset text, collection text, feature jsonb)
returns uuid language plpgsql as $disp$
declare result uuid;
begin
  execute format('select %I.%I($1)', dataset, '_' || collection || '_create')
    into result using feature;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_replace(dataset text, collection text, fid uuid, feature jsonb)
returns boolean language plpgsql as $disp$
declare result boolean;
begin
  execute format('select %I.%I($1, $2)', dataset, '_' || collection || '_replace')
    into result using fid, feature;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_update(dataset text, collection text, fid uuid, feature jsonb)
returns boolean language plpgsql as $disp$
declare result boolean;
begin
  execute format('select %I.%I($1, $2)', dataset, '_' || collection || '_update')
    into result using fid, feature;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_delete(dataset text, collection text, fid uuid)
returns boolean language plpgsql as $disp$
declare result boolean;
begin
  execute format('select %I.%I($1)', dataset, '_' || collection || '_delete')
    into result using fid;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}.feature_upsert(dataset text, collection text, feature jsonb)
returns uuid language plpgsql as $disp$
declare result uuid;
begin
  execute format('select %I.%I($1)', dataset, '_' || collection || '_upsert')
    into result using feature;
  return result;
end;
$disp$""",
    ]


def apply_dispatch(conn: psycopg.Connection) -> None:
    """Create the ``ogc.feature_*`` dispatch functions the API calls into."""
    for stmt in dispatch_statements():
        conn.execute(stmt)
    conn.commit()


# ==========================================================================
# Internal per-collection functions (generated from the description)
# ==========================================================================
def _writable_columns(table: TablePlan) -> list[ColumnPlan]:
    return [
        c
        for c in table.property_columns
        if c.name not in _AUDIT and not c.auto_increment and not c.server_write_expr
    ]


def _server_write_columns(table: TablePlan) -> list[ColumnPlan]:
    """Columns whose values are computed by the server, not read from the feature."""
    return [c for c in table.property_columns if c.server_write_expr]


def _properties_object(table: TablePlan, alias: str) -> str:
    pairs = []
    for col in table.property_columns:
        val = f'{alias}."{col.name}"'
        if col.id_inject_key:
            # Inject the row id as a sub-key into the JSONB column on read.
            val = (
                f"({val} || jsonb_build_object("
                f"'{_quote_key(col.id_inject_key)}', "
                f'{alias}."{table.id_column}"::text))'
            )
        pairs.append(f"'{_quote_key(col.name)}', {val}")
    return "jsonb_build_object(\n      " + ",\n      ".join(pairs) + "\n    )"


def _feature_object(table: TablePlan, alias: str) -> str:
    geom = table.geometry.name
    return (
        "jsonb_build_object(\n"
        "    'type', 'Feature',\n"
        f"    'id', {alias}.\"{table.id_column}\",\n"
        f"    'geometry', ST_AsGeoJSON({alias}.\"{geom}\")::jsonb,\n"
        f"    'properties', {_properties_object(table, alias)}\n"
        "  )"
    )


def _geom_from_feature(table: TablePlan) -> str:
    geom = f"ST_SetSRID(ST_GeomFromGeoJSON(feature->'geometry'), {table.geometry.srid})"
    if table.geometry.has_z:
        # Accept 2D GeoJSON into *Z columns (missing Z becomes 0).
        return f"ST_Force3D({geom})"
    return geom


def _prop_read(col: ColumnPlan) -> str:
    """SQL expression that extracts one property from the incoming feature JSON.

    For JSONB columns this applies the server-managed transforms: strips
    declared keys (e.g. the outward identifier the client must not persist)
    and injects write-time computed values (e.g. ISO timestamps).
    For scalar columns it does the original ->>'key'::type cast.
    """
    if col.sql_type == "jsonb":
        expr = f"feature->'properties'->'{_quote_key(col.name)}'"
        for key in col.strip_keys:
            # Remove server-managed sub-keys; #- takes a text-array path.
            expr = f"({expr} #- '{{{_quote_key(key)}}}')"
        for key, sql_expr in col.write_inject:
            expr = f"({expr} || jsonb_build_object('{_quote_key(key)}', {sql_expr}))"
        return expr
    return f"(feature->'properties'->>'{_quote_key(col.name)}')::{col.sql_type}"


def _enum_checks(writable: list[ColumnPlan], *, guarded_by_presence: bool) -> list[str]:
    """IF blocks that raise P0001 when a codelist field has an invalid value."""
    checks: list[str] = []
    for col in writable:
        if not col.codelist_values:
            continue
        key = _quote_key(col.name)
        values_sql = ", ".join(f"'{_quote_key(v)}'" for v in col.codelist_values)
        val_expr = f"feature->'properties'->>'{key}'"
        cond_parts: list[str] = []
        if guarded_by_presence:
            cond_parts.append(f"feature->'properties' ? '{key}'")
        cond_parts.append(f"({val_expr}) is not null")
        cond_parts.append(f"({val_expr}) not in ({values_sql})")
        cond = "\n       and ".join(cond_parts)
        checks.append(
            f"  if {cond} then\n"
            f"    raise exception 'field {col.name}: value % is not a valid code',"
            f" ({val_expr}) using errcode = 'P0001';\n"
            f"  end if;"
        )
    return checks


def _geom_checks(table: TablePlan, *, guarded_by_presence: bool) -> list[str]:
    """IF blocks that raises P0001 when the incoming geometry is not valid."""
    checks: list[str] = []
    # nullable null check
    if table.geometry.nullable:
        first_condition = "coalesce(jsonb_typeof(feature->'geometry'), 'null') not in ('object', 'null)"
    else:
        first_condition = (
            "coalesce(jsonb_typeof(feature->'geometry'), 'null') not in ('object')"
        )
    if guarded_by_presence:
        first_condition = f"feature ? 'geometry' and {first_condition}"
    checks.append(
        f"  if {first_condition} then\n"
        f"    raise exception 'missing geometry' using errcode = 'P0001';\n"
        f"  end if;"
    )

    # valid geometry check
    inner = f"not ST_IsValid({_geom_from_feature(table)})"
    checks.append(
        f"  if jsonb_typeof(feature->'geometry') = 'object' and {inner} then\n"
        f"    raise exception 'invalid geometry' using errcode = 'P0001';\n"
        f"  end if;"
    )
    return checks


def _fn_item(plan: CollectionPlan) -> str:
    t = plan.table
    return f"""\
create or replace function {plan.functions["item"]}(fid uuid)
returns jsonb language sql stable as $func$
  select {_feature_object(t, "t")}
  from {t.qualified} t
  where t."{t.id_column}" = fid;
$func$"""


def _fn_items(plan: CollectionPlan) -> str:
    t = plan.table
    geom = t.geometry.name
    # numberMatched is optional in OGC Features and costs an extra count over the
    # filtered set, so it is only computed (and only included) when with_matched.
    return f"""\
create or replace function {plan.functions["items"]}(
    bbox float8[] default null, lim int default 10, off int default 0,
    with_matched boolean default true)
returns jsonb language sql stable as $func$
  with filtered as (
    select t.* from {t.qualified} t
    where bbox is null
       or t."{geom}" && ST_MakeEnvelope(bbox[1], bbox[2], bbox[3], bbox[4], {t.geometry.srid})
  ),
  page as (select * from filtered order by "{t.id_column}" offset off limit lim)
  select jsonb_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(
      (select jsonb_agg(f) from (
         select {_feature_object(t, "p")} as f from page p
       ) sub), '[]'::jsonb),
    'numberReturned', (select count(*) from page)
  ) || case when with_matched
            then jsonb_build_object('numberMatched', (select count(*) from filtered))
            else '{{}}'::jsonb end;
$func$"""


def _fn_create(plan: CollectionPlan) -> str:
    t = plan.table
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    cols = ", ".join(
        [f'"{t.geometry.name}"']
        + [f'"{c.name}"' for c in writable]
        + [f'"{c.name}"' for c in sw]
    )
    vals = ", ".join(
        [_geom_from_feature(t)]
        + [_prop_read(c) for c in writable]
        + [c.server_write_expr for c in sw]
    )
    validations = [
        *_enum_checks(writable, guarded_by_presence=False),
        *_geom_checks(t, guarded_by_presence=False),
    ]
    guard_block = ("\n".join(validations) + "\n") if validations else ""
    return f"""\
create or replace function {plan.functions["create"]}(feature jsonb)
returns uuid language plpgsql as $func$
declare new_id uuid;
begin
{guard_block}  insert into {t.qualified} ({cols})
  values ({vals})
  returning "{t.id_column}" into new_id;
  return new_id;
end;
$func$"""


def _fn_upsert(plan: CollectionPlan) -> str:
    t = plan.table
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    conflict_path = plan.upsert_path or plan.upsert_field
    if conflict_path is None:
        raise ValueError(f"collection '{plan.collection_name}' has no upsert field")
    cols = ", ".join(
        [f'"{t.geometry.name}"']
        + [f'"{c.name}"' for c in writable]
        + [f'"{c.name}"' for c in sw]
    )
    vals = ", ".join(
        [_geom_from_feature(t)]
        + [_prop_read(c) for c in writable]
        + [c.server_write_expr for c in sw]
    )
    conflict_columns = upsert_sql_expression(conflict_path)
    sets = [f'"{t.geometry.name}" = excluded."{t.geometry.name}"']
    sets += [f'"{c.name}" = excluded."{c.name}"' for c in writable]
    sets += [f'"{c.name}" = {c.server_write_expr}' for c in sw]
    sets.append('"updated_at" = now()')
    set_clause = ",\n      ".join(sets)
    validations = [
        *_enum_checks(writable, guarded_by_presence=False),
        *_geom_checks(t, guarded_by_presence=False),
    ]
    guard_block = ("\n".join(validations) + "\n") if validations else ""
    return f"""\
create or replace function {plan.functions["upsert"]}(feature jsonb)
returns uuid language plpgsql as $func$
declare result_id uuid;
begin
{guard_block}  insert into {t.qualified} ({cols})
  values ({vals})
  on conflict ({conflict_columns}) do update set
      {set_clause}
  returning "{t.id_column}" into result_id;
  return result_id;
end;
$func$"""


def _fn_replace(plan: CollectionPlan) -> str:
    t = plan.table
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    sets = [f'"{t.geometry.name}" = {_geom_from_feature(t)}']
    sets += [f'"{c.name}" = {_prop_read(c)}' for c in writable]
    sets += [f'"{c.name}" = {c.server_write_expr}' for c in sw]
    sets.append('"updated_at" = now()')
    set_clause = ",\n      ".join(sets)
    validations = [
        *_enum_checks(writable, guarded_by_presence=False),
        *_geom_checks(t, guarded_by_presence=False),
    ]
    guard_block = ("\n".join(validations) + "\n") if validations else ""
    return f"""\
create or replace function {plan.functions["replace"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
{guard_block}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  return found;
end;
$func$"""


def _fn_update(plan: CollectionPlan) -> str:
    """Partial update: only keys present in the incoming feature change."""
    t = plan.table
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    sets = [
        f"\"{t.geometry.name}\" = case when feature ? 'geometry' "
        f'then {_geom_from_feature(t)} else "{t.geometry.name}" end'
    ]
    for c in writable:
        sets.append(
            f"\"{c.name}\" = case when feature->'properties' ? '{_quote_key(c.name)}' "
            f'then {_prop_read(c)} else "{c.name}" end'
        )
    # server_write columns are always refreshed on any write, unconditionally.
    sets += [f'"{c.name}" = {c.server_write_expr}' for c in sw]
    sets.append('"updated_at" = now()')
    set_clause = ",\n      ".join(sets)
    validations = [
        *_enum_checks(writable, guarded_by_presence=True),
        *_geom_checks(t, guarded_by_presence=True),
    ]
    guard_block = ("\n".join(validations) + "\n") if validations else ""
    return f"""\
create or replace function {plan.functions["update"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
{guard_block}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  return found;
end;
$func$"""


def _fn_delete(plan: CollectionPlan) -> str:
    t = plan.table
    return f"""\
create or replace function {plan.functions["delete"]}(fid uuid)
returns boolean language plpgsql as $func$
begin
  delete from {t.qualified} where "{t.id_column}" = fid;
  return found;
end;
$func$"""


_BUILDER_BY_OP = {
    "items": _fn_items,
    "item": _fn_item,
    "create": _fn_create,
    "replace": _fn_replace,
    "update": _fn_update,
    "delete": _fn_delete,
    "upsert": _fn_upsert,
}


def function_statements(plan: SchemaPlan) -> list[str]:
    stmts: list[str] = []
    for coll in plan.collections:
        # Only the operations this collection declares (topology = reads only).
        for op in coll.functions:
            stmts.append(_BUILDER_BY_OP[op](coll))
    return stmts


def render_functions(plan: SchemaPlan) -> str:
    return ";\n\n".join(function_statements(plan)) + ";\n"


def apply_functions(conn: psycopg.Connection, plan: SchemaPlan) -> None:
    """Create the per-collection functions the ``ogc.feature_*`` dispatch layer
    routes into (one per collection x operation).
    """
    for stmt in function_statements(plan):
        conn.execute(stmt)
    conn.commit()
