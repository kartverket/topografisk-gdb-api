from pathlib import Path

from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.descriptions.models import (
    ResolvedCollection,
    ResolvedDataset,
    ResolvedField,
)
from geocomponents.schema.build import build_schema_plan
from geocomponents.schema.functions import (
    _enum_checks,
    _prop_read,
    _properties_object,
    _quote_key,
    dispatch_statements,
    event_schema_statements,
    function_statements,
)
from geocomponents.schema.plan import (
    OPERATIONS,
    READ_OPS,
    UPSERT_OP,
    WRITE_OPS,
    CollectionPlan,
    ColumnPlan,
    GeometryColumnPlan,
    SchemaPlan,
    TablePlan,
    dispatch_function,
    internal_function,
)

DESCRIPTIONS = Path(__file__).resolve().parents[2] / "descriptions"


def _plan(name="cadastre"):
    d = next(x for x in load_resolved_datasets(DESCRIPTIONS) if x.name == name)
    return build_schema_plan(d)


def _synthetic_plan(
    *,
    fields: tuple[ResolvedField, ...],
    geometry_type: str = "Point",
    srid: int = 4326,
    has_z: bool = False,
) -> SchemaPlan:
    return build_schema_plan(
        ResolvedDataset(
            name="x",
            title="X",
            description="",
            collections=(
                ResolvedCollection(
                    name="c",
                    title="C",
                    description="",
                    feature_model="simple",
                    geometry_type=geometry_type,
                    srid=srid,
                    has_z=has_z,
                    fields=fields,
                    relationships=(),
                ),
            ),
        )
    )


def test_dispatch_exposes_all_feature_entrypoints_taking_dataset_and_collection():
    sql = "\n".join(dispatch_statements())
    for op in (*OPERATIONS, "upsert"):
        assert f"function ogc.feature_{op}(" in sql
    assert "function ogc.transaction(" in sql
    assert "function ogc.feature_delete_all(" in sql
    # The fixed entrypoints route by OGC identifiers, not physical names.
    assert "dataset text, collection text" in sql


def test_event_schema_statements_are_non_destructive_on_reapplication():
    sql = "\n".join(event_schema_statements()).lower()

    assert "create schema if not exists geocomponents_event" in sql
    assert "create table if not exists geocomponents_event.change_outbox" in sql
    assert "create index if not exists change_outbox_pending_idx" in sql
    assert "create or replace function geocomponents_event.record_change" in sql
    assert "drop schema" not in sql
    assert "drop table" not in sql


def test_dispatch_layer_is_dataset_agnostic_no_table_names_leak():
    sql = "\n".join(dispatch_statements())
    # The dispatch layer is fixed/generic: it must not mention any concrete
    # dataset, collection or table name.
    for leaked in ("cadastre", "parcels", "buildings", "blocks", "hydro", "rivers"):
        assert leaked not in sql


def test_direct_write_dispatchers_call_the_guard_helper():
    statements = dispatch_statements()
    for op in (*WRITE_OPS, UPSERT_OP):
        stmt = next(
            (
                stmt
                for stmt in statements
                if stmt.startswith(
                    f"create or replace function {dispatch_function(op)}("
                )
            ),
            None,
        )
        assert stmt is not None, f"missing dispatcher for {dispatch_function(op)}"
        assert "perform ogc._assert_direct_write_allowed(dataset, collection);" in stmt

    delete_all = next(
        stmt
        for stmt in statements
        if stmt.startswith("create or replace function ogc.feature_delete_all(")
    )
    assert (
        "perform ogc._assert_direct_write_allowed(dataset, collection);" in delete_all
    )
    assert (
        "perform set_config('geocomponents.suppress_change_events', 'on', true);"
        in delete_all
    )
    assert "lock table %I.%I in share row exclusive mode" in delete_all
    assert (
        "select array_agg(%1$I), ST_SetSRID(ST_Extent(%2$I)::geometry, $1)"
        in delete_all
    )
    assert "insert into geocomponents_event.change_outbox" in delete_all
    assert "to_regclass(format('%I.association', dataset))" in delete_all
    assert "delete from %I.association where source_collection = $1" in delete_all
    assert "execute format('delete from %I.%I', dataset, collection);" in delete_all


def test_internal_functions_match_each_collections_declared_operations():
    plan = _plan()
    stmts = "\n".join(function_statements(plan))
    for coll in plan.collections:
        for op in coll.functions:
            assert f"function {coll.functions[op]}(" in stmts


def test_topology_collection_has_internal_write_functions_for_transaction_path():
    plan = _plan()
    blocks = next(c for c in plan.collections if c.collection_name == "blocks")
    assert blocks.feature_model == "topology"
    assert set(blocks.functions) == set(READ_OPS) | {
        "create",
        "replace",
        "update",
        "delete",
    }


def test_create_function_omits_auto_increment_fields():
    plan = _synthetic_plan(
        fields=(
            ResolvedField("objid", "integer", required=True, auto_increment=True),
            ResolvedField("medium", "text"),
        )
    )
    platform = plan.collections[0]
    create_sql = next(
        stmt
        for stmt in function_statements(plan)
        if f"function {platform.functions['create']}(" in stmt
    )
    insert_columns = create_sql.split("values", maxsplit=1)[0]
    assert '"objid"' not in insert_columns


def test_upsert_function_conflicts_on_declared_business_key():
    plan = _plan("fkb_bane")
    platform = next(
        c for c in plan.collections if c.collection_name == "jernbaneplattformkant"
    )
    sql = next(
        stmt
        for stmt in function_statements(plan)
        if f"function {platform.functions['upsert']}(" in stmt
    )
    assert 'on conflict ("id")' in sql


def test_has_z_collections_force_3d_on_ingest():
    plan = _plan("fkb_bane")
    sql = "\n".join(function_statements(plan))
    assert (
        "ST_Force3D(ST_SetSRID(ST_GeomFromGeoJSON(feature->'geometry'), 5973))" in sql
    )

    cadastre_sql = "\n".join(function_statements(_plan("cadastre")))
    assert "ST_Force3D(" not in cadastre_sql


# --------------------------------------------------------------------------
# SQL-literal escaping (defense-in-depth against a name containing a quote)
# --------------------------------------------------------------------------
def test_quote_key_doubles_a_single_quote():
    assert _quote_key("O'Brien") == "O''Brien"


def test_quote_key_doubles_multiple_quotes():
    assert _quote_key("a'b'c") == "a''b''c"


def _plan_with_field_named(field_name: str) -> SchemaPlan:
    """Build a minimal SchemaPlan bypassing loader/model validation, so we can
    inject field names that the loader's SafeIdentifier would reject."""
    table = TablePlan(
        schema="s",
        name="c",
        columns=(
            ColumnPlan(
                "id",
                "uuid",
                nullable=False,
                primary_key=True,
                default="gen_random_uuid()",
            ),
            ColumnPlan(field_name, "text"),
        ),
        geometry=GeometryColumnPlan("geometry", "Point", 4326),
    )
    coll = CollectionPlan(
        collection_name="c",
        feature_model="simple",
        table=table,
        functions={op: internal_function("s", "c", op) for op in OPERATIONS},
    )
    return SchemaPlan(schema_name="s", collections=(coll,))


def test_all_three_literal_sites_escape_field_names_in_generated_sql():
    """Each of the three literal-interpolation sites lives in a different
    generated function body, so inspect each independently:

    * item body   -> _properties_object (JSON key in jsonb_build_object)
    * create body -> _prop_read         (JSON key in feature->'properties'->>'x')
    * update body -> _prop_read AND the explicit CASE-WHEN key-existence literal
    """
    plan = _plan_with_field_named("it's")
    stmts = function_statements(plan)
    by_op = {
        op: next(s for s in stmts if f"function s._c_{op}(" in s)
        for op in ("item", "create", "update")
    }
    assert "'it''s'" in by_op["item"]  # _properties_object
    assert "'it''s'" in by_op["create"]  # _prop_read
    # _fn_update contributes one via _prop_read and one via its explicit literal.
    assert by_op["update"].count("'it''s'") >= 2
    # And the unescaped 6-char literal never appears bare in any body.
    for body in stmts:
        assert "'it's'" not in body


# --------------------------------------------------------------------------
# _prop_read: JSONB write-path transformation (Commit 5)
# --------------------------------------------------------------------------


def _jsonb_col(
    name: str = "obj",
    strip_keys: tuple[str, ...] = (),
    write_inject: tuple[tuple[str, str], ...] = (),
) -> ColumnPlan:
    return ColumnPlan(name, "jsonb", strip_keys=strip_keys, write_inject=write_inject)


def test_prop_read_jsonb_bare_uses_single_arrow_not_double_arrow():
    """Suspect: bare JSONB with no strip/inject must use -> (preserving jsonb
    type), not ->> which would coerce to text and lose structure."""
    sql = _prop_read(_jsonb_col("meta"))
    assert "->'meta'" in sql
    assert "->>'meta'" not in sql


def test_prop_read_jsonb_single_strip_key_uses_hash_minus_operator():
    """Suspect: strip_key must produce a #- '{key}' path-removal expression."""
    sql = _prop_read(_jsonb_col("ids", strip_keys=("lokalid",)))
    assert "#-" in sql
    assert "lokalid" in sql


def test_prop_read_jsonb_multiple_strip_keys_are_nested():
    """Suspect: each strip_key must be a separate nested #- application;
    a single combined expression would silently drop only the last key."""
    sql = _prop_read(_jsonb_col("ids", strip_keys=("lokalid", "navnerom")))
    assert sql.count("#-") == 2
    assert "lokalid" in sql
    assert "navnerom" in sql


def test_prop_read_jsonb_write_inject_merges_computed_value():
    """Suspect: write_inject must append a || jsonb_build_object merge expression."""
    sql = _prop_read(_jsonb_col("ids", write_inject=(("versjonid", "now()::text"),)))
    assert "|| jsonb_build_object" in sql
    assert "versjonid" in sql
    assert "now()::text" in sql


# --------------------------------------------------------------------------
# _properties_object: JSONB read-path injection (Commit 5)
# --------------------------------------------------------------------------


def _table_with_cols(*extra: ColumnPlan) -> TablePlan:
    return TablePlan(
        schema="s",
        name="t",
        columns=(
            ColumnPlan(
                "id",
                "uuid",
                nullable=False,
                primary_key=True,
                default="gen_random_uuid()",
            ),
            *extra,
        ),
        geometry=GeometryColumnPlan("geometry", "Point", 4326),
    )


def test_properties_object_jsonb_with_id_inject_key_merges_row_id():
    """Suspect: id_inject_key must produce a || jsonb_build_object(key, id::text)
    merge so the row UUID appears as a named sub-field on read without being stored."""
    table = _table_with_cols(ColumnPlan("ids", "jsonb", id_inject_key="lokalid"))
    sql = _properties_object(table, "t")
    assert "jsonb_build_object('lokalid'" in sql
    assert 't."id"::text' in sql


def test_properties_object_scalar_column_not_affected_by_inject_logic():
    """Suspect: a plain scalar column must produce the bare alias.col expression;
    inject logic must not bleed across column types."""
    table = _table_with_cols(ColumnPlan("medium", "text"))
    sql = _properties_object(table, "t")
    assert "'medium', t.\"medium\"" in sql
    # jsonb_build_object only appears as the outer wrapper, not for this column.
    assert sql.count("jsonb_build_object") == 1


# --------------------------------------------------------------------------
# _enum_checks: codelist validation SQL (Commit 5)
# --------------------------------------------------------------------------


def test_enum_checks_empty_codelist_values_produces_no_checks():
    """Suspect: a column with no codelist_values must generate no IF blocks."""
    col = ColumnPlan("medium", "text", codelist_values=())
    assert _enum_checks([col], guarded_by_presence=False) == []


def test_enum_checks_unguarded_has_not_in_and_no_presence_check():
    """Suspect: guarded_by_presence=False must produce IS NOT NULL + NOT IN
    without a ? guard (create/replace always check)."""
    col = ColumnPlan("medium", "text", codelist_values=("ASFALT", "GRUS"))
    checks = _enum_checks([col], guarded_by_presence=False)
    assert len(checks) == 1
    sql = checks[0]
    assert "not in ('ASFALT', 'GRUS')" in sql
    assert "is not null" in sql
    assert "? 'medium'" not in sql


def test_enum_checks_guarded_presence_check_appears_before_null_check():
    """Suspect: guarded_by_presence=True must put the ? check first so the
    null-check doesn't evaluate on an absent key (short-circuit AND)."""
    col = ColumnPlan("medium", "text", codelist_values=("ASFALT",))
    checks = _enum_checks([col], guarded_by_presence=True)
    sql = checks[0]
    assert sql.index("? 'medium'") < sql.index("is not null")


def test_enum_checks_code_value_with_single_quote_is_escaped():
    """Suspect: code values are not SafeIdentifier-constrained, so a value
    containing a single quote must be doubled to avoid broken SQL."""
    col = ColumnPlan("field", "text", codelist_values=("O'Brien",))
    sql = _enum_checks([col], guarded_by_presence=False)[0]
    assert "'O''Brien'" in sql
    assert "'O'Brien'" not in sql


# --------------------------------------------------------------------------
# Write function integration: guard block placement (Commit 5)
# --------------------------------------------------------------------------


def _plan_with_codelist_col(codes: tuple[str, ...]) -> SchemaPlan:
    """Minimal SchemaPlan with one codelist-constrained text column."""
    table = _table_with_cols(ColumnPlan("medium", "text", codelist_values=codes))
    coll = CollectionPlan(
        collection_name="t",
        feature_model="simple",
        table=table,
        functions={op: internal_function("s", "t", op) for op in OPERATIONS},
    )
    return SchemaPlan(schema_name="s", collections=(coll,))


def _plan_with_server_write_col() -> SchemaPlan:
    """Minimal SchemaPlan with one scalar server_write_expr column."""
    table = _table_with_cols(
        ColumnPlan("medium", "text"),
        ColumnPlan("oppdateringsdato", "timestamp", server_write_expr="now()"),
    )
    coll = CollectionPlan(
        collection_name="t",
        feature_model="simple",
        table=table,
        functions={op: internal_function("s", "t", op) for op in OPERATIONS},
    )
    return SchemaPlan(schema_name="s", collections=(coll,))


def test_fn_create_enum_guard_appears_before_insert():
    """Suspect: the enum validation block must precede INSERT in the create function."""
    plan = _plan_with_codelist_col(("A", "B"))
    stmts = function_statements(plan)
    create = next(s for s in stmts if "function s._t_create(" in s)
    assert create.index("if (") < create.index("insert into")


def test_fn_update_uses_presence_guarded_enum_check_but_create_does_not():
    """Suspect: update patches only the supplied fields so validation must be
    guarded by key presence; create receives the full feature so no guard needed."""
    plan = _plan_with_codelist_col(("A", "B"))
    stmts = function_statements(plan)
    create = next(s for s in stmts if "function s._t_create(" in s)
    update = next(s for s in stmts if "function s._t_update(" in s)
    assert "? 'medium'" not in create
    assert "? 'medium'" in update


# --------------------------------------------------------------------------
# Scalar server_write_expr: excluded from writes, substituted in DML (Commit 8a)
# --------------------------------------------------------------------------


def test_server_write_col_absent_from_create_insert_values():
    """Pre-code suspect: a column with server_write_expr must NOT appear as a
    client-read value in the INSERT — the server expression is used instead."""
    plan = _plan_with_server_write_col()
    stmts = function_statements(plan)
    create = next(s for s in stmts if "function s._t_create(" in s)
    # The client value expression must not appear for this column.
    assert "(feature->'properties'->>'oppdateringsdato')" not in create
    # The server expression must appear.
    assert "now()" in create
    assert '"oppdateringsdato"' in create


def test_server_write_col_always_updated_in_patch_not_behind_case_when():
    """Pre-code suspect: a server_write_expr column must appear unconditionally
    in the update SET clause — no CASE WHEN guard, unlike client-provided fields."""
    plan = _plan_with_server_write_col()
    stmts = function_statements(plan)
    update = next(s for s in stmts if "function s._t_update(" in s)
    # server_write_expr column must appear in SET without a CASE WHEN guard.
    assert '"oppdateringsdato" = now()' in update
    assert "case when" not in update.split('"oppdateringsdato"')[1].split("\n")[0]
