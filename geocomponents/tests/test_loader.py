from pathlib import Path

import pytest
from pydantic import ValidationError

from geocomponents.descriptions.loader import (
    DescriptionError,
    load_dataset,
    load_resolved_datasets,
    resolve_dataset,
)
from geocomponents.descriptions.models import (
    Commons,
    DatasetDef,
    FieldDef,
    RelationshipDef,
)

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
    assert by_name["municipality"].sql_type == "varchar(4)"  # type_ref
    assert by_name["status"].sql_type == "text"  # codelist -> text
    assert by_name["status"].codelist == "parcel_status"


def test_relationship_resolves_to_target_collection():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    buildings = next(c for c in cad.collections if c.name == "buildings")
    assert [(r.name, r.target) for r in buildings.relationships] == [
        ("parcel", "parcels")
    ]


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


# --------------------------------------------------------------------------
# SafeIdentifier constraint on name-shaped fields (Comments 4 + 5)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_name",
    [
        "fkb-bane",  # hyphen (reviewer's flagship example)
        "ArealressursGrense",  # uppercase / mixed case
        "1cadastre",  # leading digit
        "",  # empty
        "a" * 41,  # over PG-safe length (40)
    ],
)
def test_dataset_name_rejects_invalid_sql_identifiers(bad_name):
    """Bad names surface as a ValidationError at parse time rather than a
    cryptic PG syntax failure deep in the DDL apply."""
    with pytest.raises(ValidationError):
        DatasetDef.model_validate({"name": bad_name})


def test_relationship_target_rejects_invalid_sql_identifier():
    """Relationship targets flow into SQL as table references. Rejecting at
    parse time names the field ('target') in the error, versus the resolver's
    less-specific 'unknown collection X'."""
    with pytest.raises(ValidationError):
        RelationshipDef.model_validate({"name": "r", "target": "fkb-bane"})


@pytest.mark.parametrize(
    "good_name",
    [
        "a",
        "_x",
        "cadastre",
        "arealressurs_grense",
        "a" * 40,
    ],
)
def test_safe_identifier_accepts_conformant_names(good_name):
    """Positive control for the accepted shape: snake_case up to 40 chars,
    optionally starting with an underscore, digits allowed after the first
    character."""
    ds = DatasetDef.model_validate({"name": good_name})
    assert ds.name == good_name


def test_safe_identifier_propagates_through_nested_models():
    """The constraint must apply to nested lists of models: a bad ``FieldDef``
    name inside an otherwise valid dataset should be caught at the outer
    parse, not silently accepted."""
    with pytest.raises(ValidationError):
        DatasetDef.model_validate(
            {
                "name": "ok",
                "collections": [
                    {
                        "name": "ok_coll",
                        "fields": [{"name": "bad-field", "type": "string"}],
                    }
                ],
            }
        )


def test_safe_identifier_surfaces_via_file_loader(tmp_path):
    """The constraint must fire via the file-loading path, not just via direct
    ``model_validate``. ``load_dataset`` wraps ``ValidationError`` as
    ``DescriptionError``."""
    p = tmp_path / "d.yaml"
    p.write_text("name: fkb-bane\ncollections: []\n", encoding="utf-8")
    with pytest.raises(DescriptionError):
        load_dataset(p)


# --------------------------------------------------------------------------
# FieldDef: exactly one of type / type_ref / codelist
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fld",
    [
        {"name": "f", "type": "string", "type_ref": "x"},
        {"name": "f", "type": "string", "codelist": "c"},
        {"name": "f", "type_ref": "x", "codelist": "c"},
        {"name": "f", "type": "string", "type_ref": "x", "codelist": "c"},
    ],
)
def test_field_rejects_multiple_type_sources(fld):
    """Setting more than one silently prioritized codelist > type_ref > type
    in the resolver, hiding authoring mistakes. Reject at parse time."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate(fld)


def test_field_rejects_no_type_source():
    """A field must select its column type somehow."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate({"name": "f"})
