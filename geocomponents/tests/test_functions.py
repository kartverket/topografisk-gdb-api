from pathlib import Path

from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.schema.build import build_schema_plan
from geocomponents.schema.functions import dispatch_statements, function_statements
from geocomponents.schema.plan import OPERATIONS, READ_OPS

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
