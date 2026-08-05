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

import psycopg

from geocomponents.schema.plan import (
    DISPATCH_SCHEMA,
    CollectionPlan,
    ColumnPlan,
    SchemaPlan,
    TablePlan,
)

# Audit columns are server-managed; never written from incoming features.
_AUDIT = ("created_at", "updated_at")


def _quote_key(name: str) -> str:
    """Escape single quotes so ``name`` can be embedded in a SQL literal.

    Defense-in-depth: names are already restricted by the loader's
    ``SafeIdentifier``, but hand-built plans (e.g. tests) can bypass that.
    """
    return name.replace("'", "''")


# ==========================================================================
# Dispatch layer (fixed; generated once, independent of any dataset)
# ==========================================================================
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
        if c.name not in _AUDIT and not c.auto_increment
    ]


def _properties_object(table: TablePlan, alias: str) -> str:
    pairs = [
        f"'{_quote_key(col.name)}', {alias}.\"{col.name}\""
        for col in table.property_columns
    ]
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
    return f"ST_SetSRID(ST_GeomFromGeoJSON(feature->'geometry'), {table.geometry.srid})"


def _prop_read(col: ColumnPlan) -> str:
    return f"(feature->'properties'->>'{_quote_key(col.name)}')::{col.sql_type}"


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
    cols = ", ".join([f'"{t.geometry.name}"'] + [f'"{c.name}"' for c in writable])
    vals = ", ".join([_geom_from_feature(t)] + [_prop_read(c) for c in writable])
    return f"""\
create or replace function {plan.functions["create"]}(feature jsonb)
returns uuid language plpgsql as $func$
declare new_id uuid;
begin
  insert into {t.qualified} ({cols})
  values ({vals})
  returning "{t.id_column}" into new_id;
  return new_id;
end;
$func$"""


def _fn_replace(plan: CollectionPlan) -> str:
    t = plan.table
    writable = _writable_columns(t)
    sets = [f'"{t.geometry.name}" = {_geom_from_feature(t)}']
    sets += [f'"{c.name}" = {_prop_read(c)}' for c in writable]
    sets.append('"updated_at" = now()')
    set_clause = ",\n      ".join(sets)
    return f"""\
create or replace function {plan.functions["replace"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  return found;
end;
$func$"""


def _fn_update(plan: CollectionPlan) -> str:
    """Partial update: only keys present in the incoming feature change."""
    t = plan.table
    writable = _writable_columns(t)
    sets = [
        f"\"{t.geometry.name}\" = case when feature ? 'geometry' "
        f'then {_geom_from_feature(t)} else "{t.geometry.name}" end'
    ]
    for c in writable:
        sets.append(
            f"\"{c.name}\" = case when feature->'properties' ? '{_quote_key(c.name)}' "
            f'then {_prop_read(c)} else "{c.name}" end'
        )
    sets.append('"updated_at" = now()')
    set_clause = ",\n      ".join(sets)
    return f"""\
create or replace function {plan.functions["update"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
  update {t.qualified} set
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
