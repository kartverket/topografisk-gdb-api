"""Validation tests for raw description models."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from geocomponents.descriptions.models import (
    CollectionDef,
    DatasetDef,
    DerivedAreas,
    DerivedHoles,
    FieldDef,
    GeometryDef,
)

# ---------------------------------------------------------------------------
# FieldDef — pre-code suspects
# ---------------------------------------------------------------------------


def test_object_field_with_empty_fields_raises():
    with pytest.raises(ValidationError, match="object"):
        FieldDef.model_validate({"name": "f", "type": "object"})


def test_object_field_with_type_ref_also_set_raises():
    """Suspect: type:object + type_ref → n_set==2, caught by existing check, but
    confirm explicitly so a refactor can't accidentally let it through."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate(
            {
                "name": "f",
                "type": "object",
                "type_ref": "x",
                "fields": [{"name": "sub", "type": "string"}],
            }
        )


def test_enum_alongside_type_does_not_count_as_type_source():
    fld = FieldDef.model_validate({"name": "f", "type": "string", "enum": ["a", "b"]})
    assert fld.enum == ["a", "b"]
    assert fld.type == "string"


def test_valid_object_field_with_sub_fields_parses():
    fld = FieldDef.model_validate(
        {
            "name": "kvalitet",
            "type": "object",
            "fields": [{"name": "datafangstmetode", "type": "string"}],
        }
    )
    assert fld.type == "object"
    assert len(fld.fields) == 1
    assert fld.fields[0].name == "datafangstmetode"


def test_object_field_with_nested_object_parses():
    fld = FieldDef.model_validate(
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
    )
    assert fld.fields[0].fields[0].name == "leaf"


def test_indexable_on_scalar_field_is_valid():
    fld = FieldDef.model_validate({"name": "f", "type": "string", "indexable": True})
    assert fld.indexable is True


@dataclass(frozen=True)
class DerivedGeometryRejectCase:
    id: str
    geometry: dict
    error_fragment: str


DERIVED_GEOMETRY_REJECT_CASES = [
    DerivedGeometryRejectCase(
        "unknown-derived-key-is-rejected",
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "nonesuch": "ignored-never",
                "one_of": [["boundedByOuter"]],
            },
        },
        "nonesuch",
    ),
    DerivedGeometryRejectCase(
        "one-of-must-not-be-empty",
        {
            "type": "MultiPolygon",
            "derived": {"rule": "footprint", "one_of": []},
        },
        "one_of",
    ),
    DerivedGeometryRejectCase(
        "alternatives-must-not-be-empty",
        {
            "type": "MultiPolygon",
            "derived": {"rule": "footprint", "one_of": [[]]},
        },
        "one_of",
    ),
    DerivedGeometryRejectCase(
        "areas-must-be-one-or-many",
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "areas": "two",
                "one_of": [["boundedByOuter"]],
            },
        },
        "two",
    ),
    DerivedGeometryRejectCase(
        "holes-must-be-allowed-or-forbidden",
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "holes": "maybe",
                "one_of": [["boundedByOuter"]],
            },
        },
        "maybe",
    ),
    DerivedGeometryRejectCase(
        "areas-and-holes-require-rule",
        {
            "type": "MultiPolygon",
            "derived": {
                "areas": "one",
                "holes": "allowed",
                "one_of": [["boundedByOuter"]],
            },
        },
        "rule",
    ),
    DerivedGeometryRejectCase(
        "areas-is-required",
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "holes": "allowed",
                "one_of": [["boundedByOuter"]],
            },
        },
        "areas",
    ),
    DerivedGeometryRejectCase(
        "holes-is-required",
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "areas": "one",
                "one_of": [["boundedByOuter"]],
            },
        },
        "holes",
    ),
]


def test_geometry_derived_parses_and_normalizes_members():
    geometry = GeometryDef.model_validate(
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "areas": "many",
                "holes": "allowed",
                "one_of": [
                    [
                        "boundedByOuter",
                        {"name": "boundedByFacade", "when": "is_bounding"},
                    ]
                ],
            },
        }
    )

    assert geometry.derived is not None
    assert geometry.derived.rule == "footprint"
    assert geometry.derived.areas is DerivedAreas.MANY
    assert geometry.derived.holes is DerivedHoles.ALLOWED
    assert [
        [(role.name, role.when) for role in alternative]
        for alternative in geometry.derived.one_of
    ] == [[("boundedByOuter", None), ("boundedByFacade", "is_bounding")]]


def test_geometry_derived_parses_explicit_areas_and_holes():
    geometry = GeometryDef.model_validate(
        {
            "type": "MultiPolygon",
            "derived": {
                "rule": "footprint",
                "areas": "one",
                "holes": "forbidden",
                "one_of": [["boundedByOuter"]],
            },
        }
    )

    assert geometry.derived is not None
    assert geometry.derived.areas is DerivedAreas.ONE
    assert geometry.derived.holes is DerivedHoles.FORBIDDEN


@pytest.mark.parametrize(
    "case", DERIVED_GEOMETRY_REJECT_CASES, ids=lambda case: case.id
)
def test_geometry_derived_rejects_invalid_shape(case):
    with pytest.raises(ValidationError, match=case.error_fragment):
        GeometryDef.model_validate(case.geometry)


# ---------------------------------------------------------------------------
# CollectionDef — pre-code suspects
# ---------------------------------------------------------------------------


def test_collection_server_managed_with_valid_tokens_parses():
    coll = CollectionDef.model_validate(
        {
            "name": "c",
            "outward_identifier": "identifikasjon.lokalid",
            "server_managed": {
                "identifikasjon.lokalid": "outward_identifier",
                "identifikasjon.versjonid": "timestamp_iso",
            },
        }
    )
    assert coll.outward_identifier == "identifikasjon.lokalid"
    assert coll.server_managed["identifikasjon.versjonid"] == "timestamp_iso"


def test_collection_server_managed_with_unknown_token_raises():
    """Suspect: invalid token silently accepted if token validation is missing."""
    with pytest.raises(ValidationError, match="invalid token"):
        CollectionDef.model_validate(
            {"name": "c", "server_managed": {"some.field": "UNKNOWN_TOKEN"}}
        )


# ---------------------------------------------------------------------------
# DatasetDef — pre-code suspects
# ---------------------------------------------------------------------------


def test_dataset_codelists_field_parses():
    ds = DatasetDef.model_validate(
        {
            "name": "x",
            "codelists": [{"name": "medium", "values": [{"code": "T"}]}],
        }
    )
    assert len(ds.codelists) == 1
    assert ds.codelists[0].name == "medium"
    assert ds.codelists[0].values[0].code == "T"


def test_dataset_without_codelists_still_parses():
    """Suspect: adding a required-looking field could break existing datasets that omit it."""
    ds = DatasetDef.model_validate({"name": "x"})
    assert ds.codelists == []


# ---------------------------------------------------------------------------
# Post-code suspects (found by reading the implementation)
# ---------------------------------------------------------------------------


def test_object_field_with_auto_increment_raises():
    """Post-code suspect: auto_increment check runs after the object-branch, so a
    type:object + auto_increment:true field raises — the error should mention
    'auto_increment', not leave the user confused about integer fields."""
    with pytest.raises(ValidationError, match="auto_increment"):
        FieldDef.model_validate(
            {
                "name": "f",
                "type": "object",
                "fields": [{"name": "sub", "type": "string"}],
                "auto_increment": True,
            }
        )


def test_object_field_with_type_ref_and_codelist_both_set_raises():
    """Post-code suspect: both type_ref and codelist set alongside type:object.
    The check catches either; confirm it raises (not silently uses one)."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate(
            {
                "name": "f",
                "type": "object",
                "type_ref": "x",
                "codelist": "y",
                "fields": [{"name": "sub", "type": "string"}],
            }
        )


def test_empty_enum_list_is_valid():
    """Post-code suspect: enum:[] should not trigger any validation error."""
    fld = FieldDef.model_validate({"name": "f", "type": "string", "enum": []})
    assert fld.enum == []


def test_collection_empty_server_managed_is_valid():
    """Post-code suspect: omitting server_managed should default to empty dict."""
    coll = CollectionDef.model_validate({"name": "c"})
    assert coll.server_managed == {}
    assert coll.outward_identifier is None


def test_object_field_indexable_true_at_parent_level_is_valid():
    """Post-code suspect: indexable on the parent object field itself (not a sub-field)
    must be accepted by the model (schema builder ignores it — tested later)."""
    fld = FieldDef.model_validate(
        {
            "name": "identifikasjon",
            "type": "object",
            "indexable": True,
            "fields": [{"name": "lokalid", "type": "string", "indexable": True}],
        }
    )
    assert fld.indexable is True
    assert fld.fields[0].indexable is True
