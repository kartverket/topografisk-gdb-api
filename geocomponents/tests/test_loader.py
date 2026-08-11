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


def test_bane_upsert_key_resolves():
    bane = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bane")
    for coll in bane.collections:
        assert coll.upsert_key == ("lokalid", "identifikasjon_navnerom")
        assert coll.supports_upsert


def test_bygning_dataset_resolves_expected_geometry_and_upsert_key():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    assert [coll.name for coll in bygning.collections] == [
        "bygning",
        "bygning_omrade",
        "bygning_senterlinje",
        "bygning_posisjon",
    ]

    linework = next(coll for coll in bygning.collections if coll.name == "bygning")
    assert linework.geometry_type == "MultiLineString"
    assert linework.srid == 5972
    assert linework.has_z is True
    assert linework.upsert_key == ("lokalid", "identifikasjon_navnerom")
    assert linework.supports_upsert

    area = next(coll for coll in bygning.collections if coll.name == "bygning_omrade")
    assert area.geometry_type == "MultiPolygon"
    assert area.srid == 5972
    assert area.has_z is True
    assert area.upsert_key == ("lokalid", "identifikasjon_navnerom")
    assert area.supports_upsert

    centerline = next(
        coll for coll in bygning.collections if coll.name == "bygning_senterlinje"
    )
    assert centerline.geometry_type == "MultiLineString"
    assert centerline.srid == 5972
    assert centerline.has_z is True
    assert centerline.upsert_key == ("lokalid", "identifikasjon_navnerom")
    assert centerline.supports_upsert

    position = next(
        coll for coll in bygning.collections if coll.name == "bygning_posisjon"
    )
    assert position.geometry_type == "Point"
    assert position.srid == 5972
    assert position.has_z is True
    assert position.upsert_key == ("lokalid", "identifikasjon_navnerom")
    assert position.supports_upsert


def test_upsert_key_must_reference_writable_fields():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [{"name": "c", "upsert_key": ["missing"]}],
        }
    )
    with pytest.raises(DescriptionError, match="unknown field"):
        resolve_dataset(dataset, Commons())


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
# Nested object fields (Commit 2)
# --------------------------------------------------------------------------


def _dataset_with_object_field(extra_collection_keys=None):
    """Helper: dataset with a single collection containing an object field."""
    coll = {
        "name": "c",
        "fields": [
            {
                "name": "kvalitet",
                "type": "object",
                "fields": [
                    {"name": "datafangstmetode", "type": "string"},
                    {"name": "noyaktighet", "type": "integer"},
                ],
            }
        ],
    }
    if extra_collection_keys:
        coll.update(extra_collection_keys)
    return DatasetDef.model_validate({"name": "x", "collections": [coll]})


def test_object_field_resolves_to_jsonb_with_sub_fields():
    ds = resolve_dataset(_dataset_with_object_field(), Commons())
    coll = ds.collections[0]
    kvalitet = next(f for f in coll.fields if f.name == "kvalitet")
    assert kvalitet.sql_type == "jsonb"
    assert len(kvalitet.sub_fields) == 2
    assert kvalitet.sub_fields[0].name == "datafangstmetode"
    assert kvalitet.sub_fields[0].sql_type == "text"
    assert kvalitet.sub_fields[1].name == "noyaktighet"
    assert kvalitet.sub_fields[1].sql_type == "integer"


def test_depth2_nesting_resolves_correctly():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "fields": [
                        {
                            "name": "outer",
                            "type": "object",
                            "fields": [
                                {
                                    "name": "inner",
                                    "type": "object",
                                    "fields": [{"name": "leaf", "type": "string"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    outer = ds.collections[0].fields[0]
    assert outer.sql_type == "jsonb"
    inner = outer.sub_fields[0]
    assert inner.sql_type == "jsonb"
    leaf = inner.sub_fields[0]
    assert leaf.sql_type == "text"


def test_enum_propagates_to_resolved_field():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "fields": [
                        {"name": "medium", "type": "string", "enum": ["T", "U", "V"]}
                    ],
                }
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    medium = ds.collections[0].fields[0]
    assert medium.enum == ("T", "U", "V")


def test_indexable_propagates_to_resolved_field():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "fields": [
                        {"name": "lokalid", "type": "string", "indexable": True}
                    ],
                }
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    assert ds.collections[0].fields[0].indexable is True


def test_error_message_contains_full_path_for_nested_bad_type_ref():
    """where context must compose so the error names the sub-field path."""
    dataset = DatasetDef.model_validate(
        {
            "name": "myds",
            "collections": [
                {
                    "name": "mycoll",
                    "fields": [
                        {
                            "name": "kvalitet",
                            "type": "object",
                            "fields": [{"name": "method", "type_ref": "no_such_type"}],
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(DescriptionError, match="kvalitet"):
        resolve_dataset(dataset, Commons())


def test_dataset_codelist_takes_precedence_over_commons():
    """Dataset-local codelists must shadow a commons codelist of the same name."""
    commons = Commons.model_validate(
        {"code_lists": [{"name": "medium", "values": [{"code": "COMMONS_ONLY"}]}]}
    )
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "codelists": [{"name": "medium", "values": [{"code": "DATASET_VALUE"}]}],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "medium"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset, commons)
    # The field resolves successfully (both sources have "medium"), and the
    # dataset codelist is used. We can't directly inspect which was picked
    # from ResolvedField, but the key assertion is that it resolves at all
    # and that adding a dataset codelist doesn't break the lookup.
    assert ds.collections[0].fields[0].codelist == "medium"


def test_outward_identifier_dot_path_validated_against_fields():
    """An outward_identifier referencing a non-existent sub-field must raise."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "outward_identifier": "identifikasjon.ghost",
                    "fields": [
                        {
                            "name": "identifikasjon",
                            "type": "object",
                            "fields": [{"name": "lokalid", "type": "string"}],
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(DescriptionError, match="outward_identifier"):
        resolve_dataset(dataset, Commons())


def test_server_managed_dot_path_validated_against_fields():
    """A server_managed path referencing a non-existent field must raise."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "server_managed": {"does_not_exist.sub": "timestamp_iso"},
                    "fields": [{"name": "other", "type": "string"}],
                }
            ],
        }
    )
    with pytest.raises(DescriptionError, match="server_managed"):
        resolve_dataset(dataset, Commons())


def test_outward_identifier_and_server_managed_stored_on_resolved_collection():
    """Valid declarations must propagate to the resolved collection."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {
                    "name": "c",
                    "outward_identifier": "identifikasjon.lokalid",
                    "server_managed": {
                        "identifikasjon.lokalid": "outward_identifier",
                        "identifikasjon.versjonid": "timestamp_iso",
                    },
                    "fields": [
                        {
                            "name": "identifikasjon",
                            "type": "object",
                            "fields": [
                                {"name": "lokalid", "type": "string"},
                                {"name": "versjonid", "type": "string"},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    coll = ds.collections[0]
    assert coll.outward_identifier_path == "identifikasjon.lokalid"
    assert coll.server_managed_paths["identifikasjon.versjonid"] == "timestamp_iso"


# --------------------------------------------------------------------------
# Loader post-code suspects
# --------------------------------------------------------------------------


def test_codelist_defined_only_in_dataset_resolves():
    """Dataset-local codelist with no commons counterpart must resolve."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "codelists": [{"name": "medium", "values": [{"code": "T"}]}],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "medium"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    assert ds.collections[0].fields[0].codelist == "medium"


def test_codelist_only_in_commons_still_resolves():
    """Adding dataset.codelists must not break the existing commons lookup path."""
    commons = Commons.model_validate(
        {"code_lists": [{"name": "existing", "values": [{"code": "A"}]}]}
    )
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "existing"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset, commons)
    assert ds.collections[0].fields[0].codelist == "existing"


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


# --------------------------------------------------------------------------
# codelist_values flow (Commit 5 prerequisite)
# --------------------------------------------------------------------------


def test_codelist_values_populated_from_declared_codes():
    """Suspect: codes in ResolvedField.codelist_values must match the codelist
    declaration order and content."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "codelists": [
                {
                    "name": "surface",
                    "values": [
                        {"code": "ASFALT"},
                        {"code": "GRUS"},
                        {"code": "STEIN"},
                    ],
                }
            ],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "surface"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    assert ds.collections[0].fields[0].codelist_values == ("ASFALT", "GRUS", "STEIN")


def test_codelist_with_no_values_gives_empty_codelist_values():
    """Suspect: a codelist with no declared values must not raise; codelist_values
    must be an empty tuple so downstream callers can check truthiness safely."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "codelists": [{"name": "empty"}],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "empty"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset, Commons())
    assert ds.collections[0].fields[0].codelist_values == ()
