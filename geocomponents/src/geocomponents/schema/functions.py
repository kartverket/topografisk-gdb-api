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
    CollectionRolePlan,
    ColumnPlan,
    SchemaPlan,
    TablePlan,
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

    def _write_dispatch_statement(
        operation: str,
        *,
        args: tuple[tuple[str, str], ...],
        result_type: str,
    ) -> str:
        args_sql = ", ".join(f"{name} {sql_type}" for name, sql_type in args)
        call_sql = ", ".join(f"${idx}" for idx, _ in enumerate(args, start=1))
        using_sql = ", ".join(name for name, _ in args)
        return f"""\
create or replace function {s}.feature_{operation}(dataset text, collection text, {args_sql})
returns {result_type} language plpgsql as $disp$
declare result {result_type};
begin
    perform {s}._assert_direct_write_allowed(dataset, collection);
    execute format('select %I.%I({call_sql})', dataset, '_' || collection || '_{operation}')
        into result using {using_sql};
    return result;
end;
$disp$"""

    def _comment_statement(signature: str, text: str) -> str:
        return f"comment on function {s}.{signature} is $$" + text + "$$"

    return [
        f"create schema if not exists {s}",
        f"""\
create or replace function {s}._collection_feature_model(dataset text, collection text)
returns text language plpgsql stable as $disp$
declare result text;
begin
  execute format(
    'select feature_model from %I.collection_capability where collection = $1',
    dataset)
    into result using collection;
  return result;
end;
$disp$""",
        f"""\
create or replace function {s}._assert_direct_write_allowed(dataset text, collection text)
returns void language plpgsql stable as $disp$
begin
  if {s}._collection_feature_model(dataset, collection) = 'topology' then
    raise exception 'collection % does not support direct write operations', collection
      using errcode = 'P0001';
  end if;
end;
$disp$""",
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
        _write_dispatch_statement(
            "create",
            args=(("feature", "jsonb"),),
            result_type="uuid",
        ),
        _write_dispatch_statement(
            "replace",
            args=(("fid", "uuid"), ("feature", "jsonb")),
            result_type="boolean",
        ),
        _write_dispatch_statement(
            "update",
            args=(("fid", "uuid"), ("feature", "jsonb")),
            result_type="boolean",
        ),
        _write_dispatch_statement(
            "delete",
            args=(("fid", "uuid"),),
            result_type="boolean",
        ),
        f"""\
create or replace function {s}.transaction(dataset text, document jsonb)
returns jsonb language plpgsql as $disp$
declare
    tx_items jsonb := coalesce(document->'transaction', '[]'::jsonb);
    report_items jsonb := '[]'::jsonb;
    deleted_targets jsonb := '[]'::jsonb;
    structure_findings jsonb := '[]'::jsonb;
    current_item record;
    current_action text;
    current_collection text;
    current_id text;
    current_feature jsonb;
    current_feature_model text;
    in_item boolean := false;
    structure_failed boolean := false;
    created_id uuid;
    wrote boolean;
    report_reason text := null;
begin
    perform {s}._collection_feature_model(dataset, null);

    begin
        if coalesce(document->>'semantic', '') <> 'atomic' then
            raise exception 'unsupported semantic: %', coalesce(document->>'semantic', '<null>')
                using errcode = 'P0001';
        end if;
        if jsonb_typeof(tx_items) <> 'array' then
            raise exception 'transaction must be an array' using errcode = 'P0001';
        end if;

        for current_item in
            select ordinality - 1 as item_index, value as item
            from jsonb_array_elements(tx_items) with ordinality
        loop
            in_item := true;
            current_action := current_item.item->>'action';
            current_collection := current_item.item->>'collection';
            current_feature := current_item.item->'feature';
            current_id := case
                when current_action = 'insert' then current_feature->>'id'
                else current_item.item->>'id'
            end;

            current_feature_model := {s}._collection_feature_model(dataset, current_collection);
            if current_feature_model is null then
                raise exception 'unknown collection: %', current_collection using errcode = 'P0001';
            end if;

            if current_action = 'insert' then
                execute format('select %I.%I($1)', dataset, '_' || current_collection || '_create')
                    into created_id using current_feature;
                current_id := created_id::text;
                report_items := report_items || jsonb_build_array(jsonb_build_object(
                    'index', current_item.item_index,
                    'action', current_action,
                    'collection', current_collection,
                    'id', current_id,
                    'status', 'created',
                    'sqlstate', null,
                    'reason', null));
            elsif current_action = 'replace' then
                execute format('select %I.%I($1, $2)', dataset, '_' || current_collection || '_replace')
                    into wrote using current_id::uuid, current_feature;
                if not wrote then
                    raise exception 'feature not found: %', current_id using errcode = 'P0001';
                end if;
                report_items := report_items || jsonb_build_array(jsonb_build_object(
                    'index', current_item.item_index,
                    'action', current_action,
                    'collection', current_collection,
                    'id', current_id,
                    'status', 'updated',
                    'sqlstate', null,
                    'reason', null));
            elsif current_action = 'update' then
                execute format('select %I.%I($1, $2)', dataset, '_' || current_collection || '_update')
                    into wrote using current_id::uuid, current_feature;
                if not wrote then
                    raise exception 'feature not found: %', current_id using errcode = 'P0001';
                end if;
                report_items := report_items || jsonb_build_array(jsonb_build_object(
                    'index', current_item.item_index,
                    'action', current_action,
                    'collection', current_collection,
                    'id', current_id,
                    'status', 'updated',
                    'sqlstate', null,
                    'reason', null));
            elsif current_action = 'delete' then
                execute format('select %I.%I($1)', dataset, '_' || current_collection || '_delete')
                    into wrote using current_id::uuid;
                if not wrote then
                    raise exception 'feature not found: %', current_id using errcode = 'P0001';
                end if;
                deleted_targets := deleted_targets || jsonb_build_array(jsonb_build_object(
                    'item_index', current_item.item_index,
                    'target_collection', current_collection,
                    'target_id', current_id));
                report_items := report_items || jsonb_build_array(jsonb_build_object(
                    'index', current_item.item_index,
                    'action', current_action,
                    'collection', current_collection,
                    'id', current_id,
                    'status', 'deleted',
                    'sqlstate', null,
                    'reason', null));
            else
                raise exception 'unknown action: %', coalesce(current_action, '<null>')
                    using errcode = 'P0001';
            end if;
        end loop;

        if deleted_targets <> '[]'::jsonb
           and to_regclass(format('%I.%I', dataset, 'association_role')) is not null then
            execute format(
                $q$
with deleted_rows as (
    select item_index, target_collection, target_id
    from jsonb_to_recordset($1)
         as d(item_index int, target_collection text, target_id uuid)
), deleted_sets as (
    select target_collection, array_agg(target_id order by item_index, target_id) as ids
    from deleted_rows
    group by target_collection
), missing as (
    select s.collection as source_collection,
           s.id as source_id,
           s.property,
           d.target_collection,
           s.target_id,
           r.item_index as deleted_by_item
    from deleted_sets d
    cross join lateral %1$I._sources_using(d.target_collection, d.ids) s
    join deleted_rows r
      on r.target_collection = d.target_collection
     and r.target_id = s.target_id
)
select coalesce(jsonb_agg(jsonb_build_object(
           'reason', 'missing_member',
           'source_collection', source_collection,
           'source_id', source_id::text,
           'property', property,
           'target_collection', target_collection,
           'target_id', target_id::text,
           'deleted_by_item', deleted_by_item)
       order by source_collection, source_id, property, target_collection, target_id), '[]'::jsonb)
from missing
$q$,
                dataset)
                into structure_findings using deleted_targets;
        end if;

        if structure_findings <> '[]'::jsonb then
            structure_failed := true;
            raise exception 'transaction failed structure checks' using errcode = 'P0001';
        end if;
    exception
        when syntax_error_or_access_rule_violation then
            raise;
        when others then
            if structure_failed then
                return jsonb_build_object(
                    'committed', false,
                    'phase', 'structure',
                    'reason', null,
                    'items', '[]'::jsonb,
                    'structure', structure_findings,
                    'geometry', '[]'::jsonb);
            end if;
            if in_item then
                report_items := jsonb_build_array(jsonb_build_object(
                    'index', current_item.item_index,
                    'action', current_action,
                    'collection', current_collection,
                    'id', current_id,
                    'status', 'rejected',
                    'sqlstate', sqlstate,
                    'reason', sqlerrm));
            else
                report_items := '[]'::jsonb;
                report_reason := sqlerrm;
            end if;
            return jsonb_build_object(
                'committed', false,
                'phase', 'items',
                'reason', report_reason,
                'items', report_items,
                'structure', '[]'::jsonb,
                'geometry', '[]'::jsonb);
    end;

    return jsonb_build_object(
        'committed', true,
        'phase', 'items',
        'reason', null,
        'items', report_items,
        'structure', '[]'::jsonb,
        'geometry', '[]'::jsonb);
end;
$disp$""",
        _write_dispatch_statement(
            "upsert",
            args=(("feature", "jsonb"),),
            result_type="uuid",
        ),
        _comment_statement(
            "_collection_feature_model(text, text)",
            "Return the feature_model declared for one dataset collection from <dataset>.collection_capability. "
            "Precondition: dataset must resolve to a generated dataset schema. "
            "Returns text, or NULL when the collection is unknown. "
            "Raises class 42 if the dataset capability table is missing.",
        ),
        _comment_statement(
            "_assert_direct_write_allowed(text, text)",
            "Check whether direct ogc.feature_* writes are allowed for one collection. "
            "Precondition: dataset must resolve to a generated dataset schema. "
            "Returns void. "
            "Raises P0001 for feature_model topology, where ogc.transaction is the write path. "
            "Raises class 42 for an unknown dataset or broken deployment.",
        ),
        _comment_statement(
            "feature_items(text, text, float8[], integer, integer, boolean)",
            "Return a GeoJSON FeatureCollection for one dataset collection. "
            "Precondition: dataset and collection must resolve to generated read functions. "
            "Returns a jsonb FeatureCollection. "
            "Raises if the generated read function is missing.",
        ),
        _comment_statement(
            "feature_item(text, text, uuid)",
            "Return one GeoJSON Feature for a dataset collection id. "
            "Precondition: dataset and collection must resolve to generated read functions. "
            "Returns a jsonb Feature, or NULL when the id is absent. "
            "Raises if the generated read function is missing.",
        ),
        _comment_statement(
            "feature_create(text, text, jsonb)",
            "Create one feature through the generated per-collection writer. "
            "Precondition: dataset and collection must resolve to a simple-feature collection with a generated create function. "
            "Returns the new uuid. "
            "Raises P0001 for topology collections, where ogc.transaction is the write path, and class 42 for unknown dataset or broken deployment.",
        ),
        _comment_statement(
            "feature_replace(text, text, uuid, jsonb)",
            "Replace one feature through the generated per-collection writer. "
            "Precondition: dataset and collection must resolve to a simple-feature collection with a generated replace function. "
            "Returns true when a matching feature was replaced. "
            "Raises P0001 for topology collections, where ogc.transaction is the write path, and class 42 for unknown dataset or broken deployment.",
        ),
        _comment_statement(
            "feature_update(text, text, uuid, jsonb)",
            "Patch one feature through the generated per-collection writer. "
            "Precondition: dataset and collection must resolve to a simple-feature collection with a generated update function. "
            "Returns true when a matching feature was updated. "
            "Raises P0001 for topology collections, where ogc.transaction is the write path, and class 42 for unknown dataset or broken deployment.",
        ),
        _comment_statement(
            "feature_delete(text, text, uuid)",
            "Delete one feature through the generated per-collection writer. "
            "Precondition: dataset and collection must resolve to a simple-feature collection with a generated delete function. "
            "Returns true when a matching feature was deleted. "
            "Raises P0001 for topology collections, where ogc.transaction is the write path, and class 42 for unknown dataset or broken deployment.",
        ),
        _comment_statement(
            "transaction(text, jsonb)",
            'Apply an atomic transaction document of the form {"semantic": "atomic", "transaction": [...]} where action is the closed set insert | update | replace | delete. '
            "Returns a report whose shape is documented in geocomponents/README.md. "
            "For a data problem it rolls back to a savepoint and returns committed:false carrying the rejected item or document-level reason; it does not raise. "
            "Client-supplied feature ids are honored on insert here; ogc.feature_create strips them. "
            "Raises only for an unknown dataset, or a class-42 error from an undefined function, table, or column, which signals a broken deployment rather than bad input. "
            "Relationship-write contract for each declared link property: "
            "insert writes one association row per element, target resolved by outward-identifier lookup and stored as its uuid. "
            "update replaces only the rows for properties named in the document; absent declared properties keep their rows. "
            "replace clears all declared property rows first, then re-writes those present in the document. "
            "delete removes all rows where this feature is the source."
            "A property key not declared in the description is silently ignored. "
            "Invalid link inputs raise P0001: wrong featuretype, wrong identifier key, unknown target, duplicate target.",
        ),
        _comment_statement(
            "feature_upsert(text, text, jsonb)",
            "Upsert one feature by the collection business key through the generated per-collection writer. "
            "Precondition: dataset and collection must resolve to a collection with a generated upsert function. "
            "Returns the stable uuid for the stored feature. "
            "Raises P0001 for topology collections, where ogc.transaction is the write path, and class 42 for unknown dataset, missing upsert support, or broken deployment.",
        ),
    ]


def apply_dispatch(conn: psycopg.Connection) -> None:
    """Create the ``ogc.feature_*`` dispatch functions the API calls into."""
    conn.execute("drop schema if exists ogc cascade")
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


def _scalar_properties_object(table: TablePlan, alias: str) -> str:
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


def _association_element_object(role: CollectionRolePlan, target_id_sql: str) -> str:
    return (
        "jsonb_build_object("
        f"'featuretype', '{_quote_key(role.target_collection)}', "
        f"'{_quote_key(role.oi_leaf)}', {target_id_sql}::text)"
    )


def _association_properties_object(plan: CollectionPlan, source_id_sql: str) -> str:
    if not plan.roles:
        return "'{}'::jsonb"

    selects = []
    for role in plan.roles:
        selects.append(
            "      select "
            f"'{_quote_key(role.property)}'::text as property, "
            "jsonb_agg("
            + _association_element_object(role, "a.target_id")
            + " order by a.target_id) as refs\n"
            f"      from {plan.table.schema}.association a\n"
            f"      where a.source_collection = '{_quote_key(plan.collection_name)}'\n"
            f"        and a.source_id = {source_id_sql}\n"
            f"        and a.property = '{_quote_key(role.property)}'\n"
            "      having count(*) > 0"
        )
    union_sql = "\n      union all\n".join(selects)
    return (
        "coalesce((\n"
        "      select jsonb_object_agg(property, refs)\n"
        "      from (\n"
        f"{union_sql}\n"
        "      ) link_props\n"
        "    ), '{}'::jsonb)"
    )


def _properties_object(
    plan: CollectionPlan | TablePlan, alias: str, assoc_expr: str | None = None
) -> str:
    if isinstance(plan, TablePlan):
        return _scalar_properties_object(plan, alias)

    props = _scalar_properties_object(plan.table, alias)
    if assoc_expr is None:
        assoc_expr = _association_properties_object(plan, f'{alias}."{plan.id_field}"')
    return f"({props} || coalesce({assoc_expr}, '{{}}'::jsonb))"


def _feature_object(
    plan: CollectionPlan, alias: str, assoc_expr: str | None = None
) -> str:
    table = plan.table
    geom = table.geometry.name
    return (
        "jsonb_build_object(\n"
        "    'type', 'Feature',\n"
        f"    'id', {alias}.\"{table.id_column}\",\n"
        f"    'geometry', ST_AsGeoJSON({alias}.\"{geom}\")::jsonb,\n"
        f"    'properties', {_properties_object(plan, alias, assoc_expr)}\n"
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
    """IF blocks that raise P0001 when geometry is missing, invalid, or non-simple."""
    checks: list[str] = []
    # nullable null check
    if table.geometry.nullable:
        first_condition = "coalesce(jsonb_typeof(feature->'geometry'), 'null') not in ('object', 'null')"
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

    geom_expr = _geom_from_feature(table)
    # Add Validity and simplicity checks
    checks.append(
        f"  if jsonb_typeof(feature->'geometry') = 'object' then\n"
        f"    if not ST_IsValid({geom_expr}) then\n"
        f"      raise exception 'invalid geometry' using errcode = 'P0001';\n"
        f"    end if;\n"
        f"    if not ST_IsSimple({geom_expr}) then\n"
        f"      raise exception 'non-simple geometry' using errcode = 'P0001';\n"
        f"    end if;\n"
        f"  end if;"
    )
    return checks


# ==========================================================================
# Link (association) SQL helpers
# ==========================================================================

import re as _re  # noqa: E402 — kept local; only used by _safe_var_name below


def _safe_var_name(prop: str) -> str:
    """Return a valid plpgsql identifier suffix for a property name."""
    return _re.sub(r"[^a-zA-Z0-9]", "_", prop)


def _link_declare_vars(roles: tuple[CollectionRolePlan, ...]) -> str:
    """DECLARE lines for per-property target-ID arrays."""
    if not roles:
        return ""
    lines = ["  _elem jsonb;", "  _target_id uuid;"]
    for role in roles:
        vname = _safe_var_name(role.property)
        lines.append(f"  _ids_{vname} uuid[] := array[]::uuid[];")
    return "\n".join(lines) + "\n"


def _link_validation_block(role: CollectionRolePlan) -> str:
    """Presence-guarded validation + lookup block for one link property.

    Validates shape, featuretype, identifier key, and target existence.
    Collects target uuids into _ids_<prop>; raises P0001 for duplicates.
    """
    prop = _quote_key(role.property)
    target = _quote_key(role.target_collection)
    oi_leaf = _quote_key(role.oi_leaf)
    vname = _safe_var_name(role.property)
    return f"""\
  if feature->'properties' ? '{prop}' then
    if jsonb_typeof(feature->'properties'->'{prop}') <> 'array' then
      raise exception 'property {prop}: expected array' using errcode = 'P0001';
    end if;
    for _elem in select value from jsonb_array_elements(
        feature->'properties'->'{prop}') loop
      if jsonb_typeof(_elem) <> 'object' then
        raise exception 'property {prop}: element is not an object'
          using errcode = 'P0001';
      end if;
      if (_elem->>'featuretype') is distinct from '{target}' then
        raise exception 'property {prop}: featuretype % is not {target}',
          coalesce(_elem->>'featuretype', 'null') using errcode = 'P0001';
      end if;
      if not (_elem ? '{oi_leaf}') then
        raise exception 'property {prop}: expected identifier key {oi_leaf}'
          using errcode = 'P0001';
      end if;
      select "id" into _target_id from {role.target_table}
        where {role.oi_lookup_cond};
      if not found then
        raise exception 'property {prop}: missing_member % not found in {target}',
          coalesce(_elem->>'{oi_leaf}', 'null') using errcode = 'P0001';
      end if;
      _ids_{vname} := array_append(_ids_{vname}, _target_id);
    end loop;
    if cardinality(_ids_{vname}) <>
       (select count(distinct x)::int from unnest(_ids_{vname}) t(x)) then
      raise exception 'property {prop}: duplicate target' using errcode = 'P0001';
    end if;
  end if;"""


def _link_write_patch(role: CollectionRolePlan, source: str) -> str:
    """PATCH write: delete + reinsert one property when it is named in the document."""
    prop = _quote_key(role.property)
    vname = _safe_var_name(role.property)
    src = _quote_key(source)
    return f"""\
  if feature->'properties' ? '{prop}' then
    delete from {role.target_table.rsplit(".", 1)[0]}.association
      where source_collection = '{src}' and source_id = fid
        and property = '{prop}';
    insert into {role.target_table.rsplit(".", 1)[0]}.association
        (source_collection, source_id, property, target_id)
      select '{src}', fid, '{prop}', unnest(_ids_{vname});
  end if;"""


def _link_write_create(role: CollectionRolePlan, source: str) -> str:
    """Write links after INSERT, referencing new_id."""
    prop = _quote_key(role.property)
    vname = _safe_var_name(role.property)
    src = _quote_key(source)
    return f"""\
  if feature->'properties' ? '{prop}' then
    insert into {role.target_table.rsplit(".", 1)[0]}.association
        (source_collection, source_id, property, target_id)
      select '{src}', new_id, '{prop}', unnest(_ids_{vname});
  end if;"""


def _link_clear_all(
    roles: tuple[CollectionRolePlan, ...], source: str, schema: str
) -> str:
    """PUT clear: delete all declared link properties for this feature at once."""
    props = ", ".join(f"'{_quote_key(r.property)}'" for r in roles)
    src = _quote_key(source)
    return (
        f"  delete from {schema}.association\n"
        f"    where source_collection = '{src}' and source_id = fid\n"
        f"      and property in ({props});"
    )


def _link_write_put(role: CollectionRolePlan, source: str) -> str:
    """PUT write: insert for one property after the bulk clear."""
    prop = _quote_key(role.property)
    vname = _safe_var_name(role.property)
    src = _quote_key(source)
    return f"""\
  if feature->'properties' ? '{prop}' then
    insert into {role.target_table.rsplit(".", 1)[0]}.association
        (source_collection, source_id, property, target_id)
      select '{src}', fid, '{prop}', unnest(_ids_{vname});
  end if;"""


def _link_upsert_guards(roles: tuple[CollectionRolePlan, ...]) -> str:
    """Reject any declared link property present in an upsert document."""
    checks = []
    for role in roles:
        prop = _quote_key(role.property)
        checks.append(
            f"  if feature->'properties' ? '{prop}' then\n"
            f"    raise exception 'property {prop}: upsert does not support link"
            f" properties; use ogc.transaction' using errcode = 'P0001';\n"
            f"  end if;"
        )
    return "\n".join(checks) + ("\n" if checks else "")


def _fn_associations(plan: CollectionPlan) -> str:
    if not plan.roles:
        body = (
            "  select null::text as property, null::text as target_collection, null::uuid as target_id\n"
            "  where false"
        )
    else:
        selects = []
        for role in plan.roles:
            selects.append(
                "  select "
                f"'{_quote_key(role.property)}'::text as property, "
                f"'{_quote_key(role.target_collection)}'::text as target_collection, "
                "a.target_id\n"
                f"  from {plan.table.schema}.association a\n"
                f"  where a.source_collection = '{_quote_key(plan.collection_name)}'\n"
                "    and a.source_id = fid\n"
                f"    and a.property = '{_quote_key(role.property)}'"
            )
        body = "\n  union all\n".join(selects) + "\n  order by property, target_id"
    return f"""\
create or replace function {plan.table.schema}._{plan.collection_name}_associations(fid uuid)
returns table (property text, target_collection text, target_id uuid)
language sql stable as $func$
{body};
$func$"""


def _fn_sources_using(plan: SchemaPlan) -> str:
    return f"""\
create or replace function {plan.schema_name}._sources_using(target_collection text, ids uuid[])
returns table (collection text, id uuid, property text, target_id uuid)
language sql stable as $func$
    select a.source_collection as collection,
           a.source_id as id,
           a.property,
           a.target_id
    from {plan.schema_name}.association a
    join {plan.schema_name}.association_role r
        on r.source_collection = a.source_collection
     and r.property = a.property
    where r.target_collection = _sources_using.target_collection
        and a.target_id = any(ids)
    order by collection, id, property, target_id;
$func$"""


def _fn_item(plan: CollectionPlan) -> str:
    t = plan.table
    return f"""\
create or replace function {plan.functions["item"]}(fid uuid)
returns jsonb language sql stable as $func$
    with link_props as (
        select {_association_properties_object(plan, "fid")} as props
    )
    select {_feature_object(plan, "t", "link_props.props")}
  from {t.qualified} t
    cross join link_props
  where t."{t.id_column}" = fid;
$func$"""


def _fn_items(plan: CollectionPlan) -> str:
    t = plan.table
    geom = t.geometry.name
    links_cte = ""
    links_join = ""
    assoc_expr = "null"
    if plan.roles:
        selects = []
        for role in plan.roles:
            selects.append(
                "    select a.source_id, "
                f"'{_quote_key(role.property)}'::text as property, "
                "jsonb_agg("
                + _association_element_object(role, "a.target_id")
                + " order by a.target_id) as refs\n"
                f"    from {t.schema}.association a\n"
                f"    where a.source_collection = '{_quote_key(plan.collection_name)}'\n"
                f"      and a.property = '{_quote_key(role.property)}'\n"
                f'      and a.source_id in (select "{t.id_column}" from page)\n'
                "    group by a.source_id"
            )
        links_cte = (
            ",\n  page_links as (\n"
            "    select source_id, jsonb_object_agg(property, refs) as props\n"
            "    from (\n" + "\n    union all\n".join(selects) + "\n    ) link_rows\n"
            "    group by source_id\n"
            "  )"
        )
        links_join = (
            f'\n         left join page_links l on l.source_id = p."{t.id_column}"'
        )
        assoc_expr = "l.props"
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
    page as (select * from filtered order by "{t.id_column}" offset off limit lim){links_cte}
  select jsonb_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(
      (select jsonb_agg(f) from (
                 select {_feature_object(plan, "p", assoc_expr)} as f from page p{links_join}
       ) sub), '[]'::jsonb),
    'numberReturned', (select count(*) from page)
  ) || case when with_matched
            then jsonb_build_object('numberMatched', (select count(*) from filtered))
            else '{{}}'::jsonb end;
$func$"""


def _oi_column(table: TablePlan) -> ColumnPlan | None:
    """Return the JSONB column carrying the outward-identifier sub-key, or None."""
    return next((c for c in table.property_columns if c.id_inject_key), None)


def _fn_create(plan: CollectionPlan) -> str:
    t = plan.table
    oi = _oi_column(t)
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    cols = ", ".join(
        [f'"{t.id_column}"', f'"{t.geometry.name}"']
        + [f'"{c.name}"' for c in writable]
        + [f'"{c.name}"' for c in sw]
    )
    if oi:
        col_key = _quote_key(oi.name)
        sub_key = _quote_key(oi.id_inject_key)
        oi_declare = (
            f"  _oi_raw text := feature->'properties'->'{col_key}'->>'{sub_key}';\n"
        )
        oi_resolve = (
            "  if (feature->>'id') is not null and _oi_raw is not null\n"
            "     and (feature->>'id') <> _oi_raw then\n"
            "    raise exception 'feature.id and outward identifier disagree: %, %',\n"
            "      feature->>'id', _oi_raw using errcode = 'P0001';\n"
            "  end if;\n"
            "  new_id := coalesce((feature->>'id')::uuid, _oi_raw::uuid, gen_random_uuid());\n"
        )
        id_val = "new_id"
    else:
        oi_declare = ""
        oi_resolve = ""
        id_val = "coalesce((feature->>'id')::uuid, gen_random_uuid())"
    vals = ", ".join(
        [id_val, _geom_from_feature(t)]
        + [_prop_read(c) for c in writable]
        + [c.server_write_expr for c in sw]
    )
    validations = [
        *_enum_checks(writable, guarded_by_presence=False),
        *_geom_checks(t, guarded_by_presence=False),
    ]
    guard_block = ("\n".join(validations) + "\n") if validations else ""
    roles = plan.roles
    declare_extra = _link_declare_vars(roles)
    declare = (
        f"declare new_id uuid;\n{oi_declare}{declare_extra}"
        if (oi_declare or declare_extra)
        else "declare new_id uuid;"
    )
    link_validate = "\n".join(_link_validation_block(r) for r in roles)
    link_validate_block = (link_validate + "\n") if link_validate else ""
    link_write = "\n".join(_link_write_create(r, plan.collection_name) for r in roles)
    link_write_block = ("\n" + link_write) if link_write else ""
    return f"""\
create or replace function {plan.functions["create"]}(feature jsonb)
returns uuid language plpgsql as $func$
{declare}
begin
{guard_block}{link_validate_block}{oi_resolve}  insert into {t.qualified} ({cols})
  values ({vals})
  returning "{t.id_column}" into new_id;{link_write_block}
  return new_id;
end;
$func$"""


def _fn_upsert(plan: CollectionPlan) -> str:
    t = plan.table
    oi = _oi_column(t)
    writable = _writable_columns(t)
    sw = _server_write_columns(t)
    cols = ", ".join(
        [f'"{t.id_column}"', f'"{t.geometry.name}"']
        + [f'"{c.name}"' for c in writable]
        + [f'"{c.name}"' for c in sw]
    )
    if oi:
        col_key = _quote_key(oi.name)
        sub_key = _quote_key(oi.id_inject_key)
        oi_declare = (
            f"  _oi_raw text := feature->'properties'->'{col_key}'->>'{sub_key}';\n"
        )
        oi_resolve = (
            "  if _oi_raw is null and (feature->>'id') is null then\n"
            "    raise exception 'upsert requires an identifier' using errcode = 'P0001';\n"
            "  end if;\n"
            "  if (feature->>'id') is not null and _oi_raw is not null\n"
            "     and (feature->>'id') <> _oi_raw then\n"
            "    raise exception 'feature.id and outward identifier disagree: %, %',\n"
            "      feature->>'id', _oi_raw using errcode = 'P0001';\n"
            "  end if;\n"
            "  result_id := coalesce((feature->>'id')::uuid, _oi_raw::uuid);\n"
        )
        id_val = "result_id"
    else:
        oi_declare = ""
        oi_resolve = ""
        id_val = "coalesce((feature->>'id')::uuid, gen_random_uuid())"
    vals = ", ".join(
        [id_val, _geom_from_feature(t)]
        + [_prop_read(c) for c in writable]
        + [c.server_write_expr for c in sw]
    )
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
    upsert_guards = _link_upsert_guards(plan.roles)
    declare = (
        f"declare result_id uuid;\n{oi_declare}"
        if oi_declare
        else "declare result_id uuid;"
    )
    return f"""\
create or replace function {plan.functions["upsert"]}(feature jsonb)
returns uuid language plpgsql as $func$
{declare}
begin
{upsert_guards}{guard_block}{oi_resolve}  insert into {t.qualified} ({cols})
  values ({vals})
  on conflict ("{t.id_column}") do update set
      {set_clause}
  returning "{t.id_column}" into result_id;
  return result_id;
end;
$func$"""


def _fn_replace(plan: CollectionPlan) -> str:
    t = plan.table
    oi = _oi_column(t)
    roles = plan.roles
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
    if oi:
        col_key = _quote_key(oi.name)
        sub_key = _quote_key(oi.id_inject_key)
        oi_guard = (
            f"  if (feature->'properties'->'{col_key}'->>'{sub_key}') is not null\n"
            f"     and (feature->'properties'->'{col_key}'->>'{sub_key}') <> fid::text then\n"
            f"    raise exception 'outward identifier does not match' using errcode = 'P0001';\n"
            f"  end if;\n"
        )
    else:
        oi_guard = ""
    declare_extra = _link_declare_vars(roles)
    declare_block = ("declare\n" + declare_extra) if declare_extra else ""
    link_validate = "\n".join(_link_validation_block(r) for r in roles)
    link_validate_block = (link_validate + "\n") if link_validate else ""
    link_clear = (
        (_link_clear_all(roles, plan.collection_name, t.schema) + "\n") if roles else ""
    )
    link_inserts = "\n".join(_link_write_put(r, plan.collection_name) for r in roles)
    link_inserts_block = (link_inserts + "\n") if link_inserts else ""
    return (
        f"""\
create or replace function {plan.functions["replace"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
{declare_block}
begin
{guard_block}{oi_guard}{link_validate_block}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  if not found then return false; end if;
{link_clear}{link_inserts_block}  return true;
end;
$func$"""
        if roles
        else f"""\
create or replace function {plan.functions["replace"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
{guard_block}{oi_guard}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  return found;
end;
$func$"""
    )


def _fn_update(plan: CollectionPlan) -> str:
    """Partial update: only keys present in the incoming feature change."""
    t = plan.table
    oi = _oi_column(t)
    roles = plan.roles
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
    if oi:
        col_key = _quote_key(oi.name)
        sub_key = _quote_key(oi.id_inject_key)
        oi_guard = (
            f"  if (feature->'properties'->'{col_key}'->>'{sub_key}') is not null\n"
            f"     and (feature->'properties'->'{col_key}'->>'{sub_key}') <> fid::text then\n"
            f"    raise exception 'outward identifier does not match' using errcode = 'P0001';\n"
            f"  end if;\n"
        )
    else:
        oi_guard = ""
    declare_extra = _link_declare_vars(roles)
    declare_block = ("declare\n" + declare_extra) if declare_extra else ""
    link_validate = "\n".join(_link_validation_block(r) for r in roles)
    link_validate_block = (link_validate + "\n") if link_validate else ""
    link_patch = "\n".join(_link_write_patch(r, plan.collection_name) for r in roles)
    link_patch_block = (link_patch + "\n") if link_patch else ""
    return (
        f"""\
create or replace function {plan.functions["update"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
{declare_block}
begin
{guard_block}{oi_guard}{link_validate_block}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  if not found then return false; end if;
{link_patch_block}  return true;
end;
$func$"""
        if roles
        else f"""\
create or replace function {plan.functions["update"]}(fid uuid, feature jsonb)
returns boolean language plpgsql as $func$
begin
{guard_block}{oi_guard}  update {t.qualified} set
      {set_clause}
  where "{t.id_column}" = fid;
  return found;
end;
$func$"""
    )


def _fn_delete(plan: CollectionPlan) -> str:
    t = plan.table
    src = _quote_key(plan.collection_name)
    link_delete = (
        (
            f"  delete from {t.schema}.association\n"
            f"    where source_collection = '{src}' and source_id = fid;\n"
        )
        if plan.roles
        else ""
    )
    return f"""\
create or replace function {plan.functions["delete"]}(fid uuid)
returns boolean language plpgsql as $func$
begin
{link_delete}  delete from {t.qualified} where "{t.id_column}" = fid;
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
    if plan.association_role_rows:
        stmts.append(_fn_sources_using(plan))
    for coll in plan.collections:
        if coll.roles:
            stmts.append(_fn_associations(coll))
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
