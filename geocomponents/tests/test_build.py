from pathlib import Path

from geocomp.descriptions.loader import load_resolved_datasets
from geocomp.schema.build import build_schema_plan
from geocomp.schema.plan import OPERATIONS, READ_OPS

DESCRIPTIONS = Path(__file__).resolve().parents[1] / "descriptions"


def _cadastre_plan():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    return build_schema_plan(cad)


def test_dataset_maps_to_schema_and_collections_to_tables():
    plan = _cadastre_plan()
    assert plan.schema_name == "cadastre"
    assert {c.collection_name for c in plan.collections} == {
        "parcels", "buildings", "blocks"
    }
    for coll in plan.collections:
        assert coll.table.qualified == f"cadastre.{coll.collection_name}"


def test_topology_collection_gets_a_table_but_only_read_ops():
    plan = _cadastre_plan()
    blocks = next(c for c in plan.collections if c.collection_name == "blocks")
    # It still has a table (reads need one), but no write functions.
    assert blocks.table.qualified == "cadastre.blocks"
    assert set(blocks.functions) == set(READ_OPS)


def test_standard_columns_and_geometry_present():
    plan = _cadastre_plan()
    parcels = next(c for c in plan.collections if c.collection_name == "parcels")
    names = {col.name for col in parcels.table.columns}
    assert {"id", "created_at", "updated_at"} <= names
    assert parcels.table.id_column == "id"
    assert parcels.table.geometry.geometry_type == "MultiPolygon"
    assert parcels.table.geometry.srid == 4326


def test_relationship_becomes_fk_column():
    plan = _cadastre_plan()
    buildings = next(c for c in plan.collections if c.collection_name == "buildings")
    assert "parcel_id" in {col.name for col in buildings.table.columns}
    fks = {(fk.column, fk.ref_table) for fk in buildings.table.foreign_keys}
    assert ("parcel_id", "cadastre.parcels") in fks


def test_internal_function_names_are_private_and_per_operation():
    plan = _cadastre_plan()
    parcels = next(c for c in plan.collections if c.collection_name == "parcels")
    assert set(parcels.functions) == set(OPERATIONS)
    # Internal (private) names live in the dataset schema, prefixed with '_'.
    assert parcels.functions["items"] == "cadastre._parcels_items"
