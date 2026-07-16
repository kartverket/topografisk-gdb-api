from pathlib import Path

from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.schema.build import build_schema_plan
from geocomponents.schema.functions import (
    _quote_key,
    dispatch_statements,
    function_statements,
)
from geocomponents.schema.plan import (
    OPERATIONS,
    READ_OPS,
    CollectionPlan,
    ColumnPlan,
    GeometryColumnPlan,
    SchemaPlan,
    TablePlan,
    internal_function,
)

DESCRIPTIONS = Path(__file__).resolve().parents[1] / "descriptions"


def _plan(name="cadastre"):
    d = next(x for x in load_resolved_datasets(DESCRIPTIONS) if x.name == name)
    return build_schema_plan(d)


def test_dispatch_exposes_the_six_feature_entrypoints_taking_dataset_and_collection():
    sql = "\n".join(dispatch_statements())
    for op in OPERATIONS:
        assert f"function ogc.feature_{op}(" in sql
    # The fixed entrypoints route by OGC identifiers, not physical names.
    assert "dataset text, collection text" in sql


def test_dispatch_layer_is_dataset_agnostic_no_table_names_leak():
    sql = "\n".join(dispatch_statements())
    # The dispatch layer is fixed/generic: it must not mention any concrete
    # dataset, collection or table name.
    for leaked in ("cadastre", "parcels", "buildings", "blocks", "hydro", "rivers"):
        assert leaked not in sql


def test_internal_functions_match_each_collections_declared_operations():
    plan = _plan()
    stmts = "\n".join(function_statements(plan))
    # Simple collections get all ops; topology collections only reads.
    for coll in plan.collections:
        for op in coll.functions:
            assert f"function {coll.functions[op]}(" in stmts


def test_topology_collection_has_reads_only():
    plan = _plan()
    blocks = next(c for c in plan.collections if c.collection_name == "blocks")
    assert set(blocks.functions) == set(READ_OPS)


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
