from pathlib import Path

import pytest

from geocomponents.descriptions.loader import (
    DescriptionError,
    load_resolved_datasets,
    resolve_dataset,
)
from geocomponents.descriptions.models import Commons, DatasetDef

DESCRIPTIONS = Path(__file__).resolve().parents[1] / "descriptions"


def test_commons_base_field_is_inherited_by_every_collection():
    datasets = load_resolved_datasets(DESCRIPTIONS)
    for d in datasets:
        for coll in d.collections:
            assert "source" in {f.name for f in coll.fields}, coll.name


def test_type_ref_and_codelist_resolve_to_sql_types():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    parcels = next(c for c in cad.collections if c.name == "parcels")
    by_name = {f.name: f for f in parcels.fields}
    assert by_name["municipality"].sql_type == "varchar(4)"   # type_ref
    assert by_name["status"].sql_type == "text"               # codelist -> text
    assert by_name["status"].codelist == "parcel_status"


def test_relationship_resolves_to_target_collection():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    buildings = next(c for c in cad.collections if c.name == "buildings")
    assert [(r.name, r.target) for r in buildings.relationships] == [("parcel", "parcels")]


def test_unknown_type_ref_raises_clear_error():
    commons = Commons()
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {"name": "c", "fields": [{"name": "f", "type_ref": "nope"}]}
            ],
        }
    )
    with pytest.raises(DescriptionError, match="unknown type 'nope'"):
        resolve_dataset(dataset, commons)


def test_relationship_to_unknown_collection_raises():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {"name": "c", "relationships": [{"name": "r", "target": "ghost"}]}
            ],
        }
    )
    with pytest.raises(DescriptionError, match="unknown collection 'ghost'"):
        resolve_dataset(dataset, Commons())


def test_feature_model_and_processes_resolve():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    assert cad.processes == ("hello",)
    by_name = {c.name: c for c in cad.collections}
    assert by_name["parcels"].feature_model == "simple"
    assert by_name["parcels"].supports_crud is True
    assert by_name["blocks"].feature_model == "topology"
    assert by_name["blocks"].supports_crud is False


def test_unknown_process_raises_clear_error():
    dataset = DatasetDef.model_validate({"name": "x", "processes": ["nope"]})
    with pytest.raises(DescriptionError, match="unknown process"):
        resolve_dataset(dataset, Commons())
