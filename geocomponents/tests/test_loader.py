from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from geocomponents.descriptions.loader import (
    DescriptionError,
    load_dataset,
    load_resolved_datasets,
    resolve_dataset,
)
from geocomponents.descriptions.models import (
    DatasetDef,
    FieldDef,
    RelationshipDef,
)
from geocomponents.schema.build import build_schema_plan

DESCRIPTIONS = Path(__file__).resolve().parents[2] / "descriptions"
TOPOLOGY_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "topology_fixture.yaml"
)


@dataclass(frozen=True)
class CollectionNameCase:
    id: str
    collection_name: str
    error_fragment: str | None


COLLECTION_NAME_CASES = [
    CollectionNameCase("association-is-reserved", "association", "association"),
    CollectionNameCase(
        "association-role-is-reserved",
        "association_role",
        "association_role",
    ),
    CollectionNameCase("association-kind-is-allowed", "association_kind", None),
]


@dataclass(frozen=True)
class DerivedResolveCase:
    id: str
    raw: dict
    collection_name: str
    expected: (
        tuple[str, str, tuple[tuple[tuple[str, str, str | None], ...], ...]] | None
    )


@dataclass(frozen=True)
class DerivedRejectCase:
    id: str
    raw: dict
    error_fragment: str


@dataclass(frozen=True)
class BoundsResolveCase:
    id: str
    raw: dict
    collection_name: str
    expected: int | None


@dataclass(frozen=True)
class BoundsRejectCase:
    id: str
    raw: dict
    error_fragment: str
    error_type: type[Exception]


@dataclass(frozen=True)
class ExtraKeyRejectCase:
    id: str
    raw: dict
    error_fragment: str


def _topology_fixture_raw() -> dict:
    return yaml.safe_load(TOPOLOGY_FIXTURE.read_text(encoding="utf-8"))


def _with_surface_derived(
    one_of: list[list[object]],
    *,
    areas: str | None = "one",
    holes: str | None = "allowed",
) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    surface = next(coll for coll in raw["collections"] if coll["name"] == "surface")
    derived = {"rule": "footprint", "one_of": one_of}
    if areas is not None:
        derived["areas"] = areas
    if holes is not None:
        derived["holes"] = holes
    surface["geometry"]["derived"] = derived
    return raw


def _with_border4_when_field(flag_type: str) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    border4 = next(coll for coll in raw["collections"] if coll["name"] == "border4")
    border4["fields"] = [{"name": "is_bounding", "type": flag_type}]
    return raw


def _with_target_geometry(
    collection_name: str,
    *,
    geometry_type: str | None = None,
) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    target = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    if geometry_type is not None:
        target["geometry"]["type"] = geometry_type
    return raw


def _with_collection_bounds(collection_name: str, bounds) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    target = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    if bounds is None:
        target.pop("bounds", None)
    else:
        target["bounds"] = bounds
    return raw


def _with_collection_extra_key(collection_name: str, key: str, value) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    target = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    target[key] = value
    return raw


def _with_geometry_extra_key(collection_name: str, key: str, value) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    target = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    target["geometry"][key] = value
    return raw


def _with_field_extra_key(
    collection_name: str, field_name: str, key: str, value
) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    target = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    field = next(fld for fld in target["fields"] if fld["name"] == field_name)
    field[key] = value
    return raw


def _with_dataset_extra_key(key: str, value) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    raw[key] = value
    return raw


def _without_derived_shape(collection_name: str) -> dict:
    raw = deepcopy(_topology_fixture_raw())
    collection = next(
        coll for coll in raw["collections"] if coll["name"] == collection_name
    )
    del collection["geometry"]["derived"]["areas"]
    del collection["geometry"]["derived"]["holes"]
    return raw


DERIVED_RESOLVE_CASES = [
    DerivedResolveCase(
        "areas-one-and-holes-allowed-resolve",
        _with_surface_derived(
            [["boundedByOuter", "boundedByShared"]],
            areas="one",
            holes="allowed",
        ),
        "surface",
        (
            "one",
            "allowed",
            (
                (
                    ("boundedByOuter", "border1", None),
                    ("boundedByShared", "border2", None),
                ),
            ),
        ),
    ),
    DerivedResolveCase(
        "areas-many-and-holes-forbidden-resolve",
        _with_surface_derived(
            [["boundedByOuter", "boundedByShared"]],
            areas="many",
            holes="forbidden",
        ),
        "surface",
        (
            "many",
            "forbidden",
            (
                (
                    ("boundedByOuter", "border1", None),
                    ("boundedByShared", "border2", None),
                ),
            ),
        ),
    ),
    DerivedResolveCase(
        "fixture-surface-explicit-areas-and-holes-resolve",
        _topology_fixture_raw(),
        "surface",
        (
            "one",
            "allowed",
            (
                (
                    ("boundedByOuter", "border1", None),
                    ("boundedByShared", "border2", None),
                ),
                (("boundedByConditional", "border4", "is_bounding"),),
            ),
        ),
    ),
    DerivedResolveCase(
        "fixture-surface2-explicit-areas-and-holes-resolve",
        _topology_fixture_raw(),
        "surface2",
        ("many", "forbidden", ((("boundedByOuter", "border1", None),),)),
    ),
]


DERIVED_REJECT_CASES = [
    DerivedRejectCase(
        "omitted-areas-and-holes-on-required-surface-are-rejected",
        _without_derived_shape("surface"),
        "areas",
    ),
    DerivedRejectCase(
        "omitted-areas-and-holes-on-optional-surface-are-rejected",
        _without_derived_shape("surface2"),
        "areas",
    ),
    DerivedRejectCase(
        "undeclared-property-is-rejected",
        _with_surface_derived([["boundedByGhost", "boundedByShared"]]),
        "boundedByGhost",
    ),
    DerivedRejectCase(
        "unknown-when-field-is-rejected",
        _with_surface_derived(
            [
                [
                    {"name": "boundedByConditional", "when": "missing_flag"},
                    "boundedByShared",
                ]
            ]
        ),
        "missing_flag",
    ),
    DerivedRejectCase(
        "non-boolean-when-field-is-rejected",
        _with_border4_when_field("string"),
        "is_bounding",
    ),
    DerivedRejectCase(
        "non-line-target-geometry-is-rejected",
        _with_target_geometry("border1", geometry_type="Point"),
        "Point",
    ),
]


BOUNDS_RESOLVE_CASES = [
    BoundsResolveCase(
        "bounds-one-reaches-plan",
        _topology_fixture_raw(),
        "border1",
        1,
    ),
    BoundsResolveCase(
        "bounds-two-reaches-plan",
        _topology_fixture_raw(),
        "border2",
        2,
    ),
    BoundsResolveCase(
        "missing-bounds-records-no-rule",
        _topology_fixture_raw(),
        "NotatÅ",
        None,
    ),
    BoundsResolveCase(
        "targeted-only-by-non-boundary-is-accepted",
        _with_collection_bounds("NotatÅ", 1),
        "NotatÅ",
        1,
    ),
]


BOUNDS_REJECT_CASES = [
    BoundsRejectCase(
        "negative-bounds-is-rejected",
        _with_collection_bounds("border1", -1),
        "-1",
        ValidationError,
    ),
    BoundsRejectCase(
        "string-bounds-is-rejected",
        _with_collection_bounds("border1", "two"),
        "two",
        ValidationError,
    ),
    BoundsRejectCase(
        "zero-bounds-is-rejected",
        _with_collection_bounds("border1", 0),
        "0",
        ValidationError,
    ),
    BoundsRejectCase(
        "untargeted-collection-bounds-is-rejected",
        _with_collection_bounds("surface", 1),
        "surface",
        DescriptionError,
    ),
    BoundsRejectCase(
        "non-line-collection-bounds-is-rejected",
        _with_target_geometry("border1", geometry_type="MultiPolygon"),
        "MultiPolygon",
        DescriptionError,
    ),
]


EXTRA_KEY_REJECT_CASES = [
    ExtraKeyRejectCase(
        "dataset-extra-key-is-rejected",
        _with_dataset_extra_key("nonsense_key", "hi"),
        "nonsense_key",
    ),
    ExtraKeyRejectCase(
        "collection-extra-key-is-rejected",
        _with_collection_extra_key("border1", "nonsense_key", "hi"),
        "nonsense_key",
    ),
    ExtraKeyRejectCase(
        "geometry-extra-key-is-rejected",
        _with_geometry_extra_key("border1", "bounds", 1),
        "bounds",
    ),
    ExtraKeyRejectCase(
        "field-extra-key-is-rejected",
        _with_field_extra_key("border1", "label", "nonsense_key", True),
        "nonsense_key",
    ),
]


def _derived_shape(
    coll,
) -> tuple[str, str, tuple[tuple[tuple[str, str, str | None], ...], ...]] | None:
    if coll.derived is None:
        return None
    return (
        coll.derived.areas.value,
        coll.derived.holes.value,
        tuple(
            tuple((role.property, role.target, role.when_field) for role in alternative)
            for alternative in coll.derived.one_of
        ),
    )


@pytest.mark.parametrize("case", BOUNDS_RESOLVE_CASES, ids=lambda case: case.id)
def test_collection_bounds_resolve_and_reach_plan(case):
    resolved = resolve_dataset(DatasetDef.model_validate(case.raw))
    coll = next(c for c in resolved.collections if c.name == case.collection_name)
    assert coll.bounds == case.expected

    plan = build_schema_plan(resolved)
    plan_coll = next(
        c for c in plan.collections if c.collection_name == case.collection_name
    )
    assert plan_coll.bounds == case.expected


@pytest.mark.parametrize("case", BOUNDS_REJECT_CASES, ids=lambda case: case.id)
def test_collection_bounds_reject_invalid_shape_or_resolution(case):
    with pytest.raises(case.error_type, match=case.error_fragment):
        dataset = DatasetDef.model_validate(case.raw)
        resolve_dataset(dataset)


@pytest.mark.parametrize("case", EXTRA_KEY_REJECT_CASES, ids=lambda case: case.id)
def test_unknown_description_keys_are_rejected(case):
    with pytest.raises(ValidationError, match=case.error_fragment):
        DatasetDef.model_validate(case.raw)


def test_string_length_and_codelist_resolve_to_sql_types():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    parcels = next(c for c in cad.collections if c.name == "parcels")
    by_name = {f.name: f for f in parcels.fields}
    assert by_name["municipality"].sql_type == "varchar(4)"
    assert by_name["status"].sql_type == "text"  # codelist -> text
    assert by_name["status"].codelist == "parcel_status"


def test_relationship_resolves_to_target_collection():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    buildings = next(c for c in cad.collections if c.name == "buildings")
    assert [(r.property, r.target) for r in buildings.relationships] == [
        ("parcel", "parcels")
    ]


def test_relationship_to_unknown_collection_raises():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
            "collections": [
                {"name": "c", "relationships": [{"property": "r", "target": "ghost"}]}
            ],
        }
    )
    with pytest.raises(DescriptionError, match="unknown collection 'ghost'"):
        resolve_dataset(dataset)


@pytest.mark.parametrize("geometry_type", ["LineString", "Point"])
def test_footprint_derived_geometry_requires_multipolygon(geometry_type, tmp_path):
    path = tmp_path / "bad-derived.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "name": "x",
                "srid": 4326,
                "collections": [
                    {
                        "name": "surface",
                        "geometry": {
                            "type": geometry_type,
                            "derived": {
                                "rule": "footprint",
                                "areas": "one",
                                "holes": "allowed",
                                "one_of": [["boundedByOuter"]],
                            },
                        },
                        "relationships": [
                            {"property": "boundedByOuter", "target": "border"}
                        ],
                    },
                    {"name": "border", "geometry": {"type": "LineString"}},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(DescriptionError, match="MultiPolygon"):
        load_dataset(path)


@pytest.mark.parametrize("case", DERIVED_RESOLVE_CASES, ids=lambda case: case.id)
def test_collection_derived_resolves(case):
    resolved = resolve_dataset(DatasetDef.model_validate(case.raw))
    coll = next(c for c in resolved.collections if c.name == case.collection_name)
    assert _derived_shape(coll) == case.expected


@pytest.mark.parametrize("case", DERIVED_REJECT_CASES, ids=lambda case: case.id)
def test_collection_derived_rejects_invalid_resolution(case):
    expectation = (
        pytest.raises(ValidationError, match=case.error_fragment)
        if case.error_fragment in {"areas", "holes"}
        else pytest.raises(DescriptionError, match=case.error_fragment)
    )
    with expectation:
        dataset = DatasetDef.model_validate(case.raw)
        resolve_dataset(dataset)


@pytest.mark.parametrize("case", COLLECTION_NAME_CASES, ids=lambda case: case.id)
def test_collection_name_reserves_generated_table_names(case):
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
            "collections": [{"name": case.collection_name}],
        }
    )
    expectation = (
        pytest.raises(DescriptionError, match=case.error_fragment)
        if case.error_fragment is not None
        else nullcontext()
    )
    with expectation:
        resolve_dataset(dataset)


def test_existing_descriptions_still_resolve_with_reserved_name_guard():
    datasets = load_resolved_datasets(DESCRIPTIONS)
    assert datasets


def test_topology_fixture_resolves_with_bounds_and_strict_models():
    dataset = DatasetDef.model_validate(_topology_fixture_raw())
    resolved = resolve_dataset(dataset)
    assert [coll.name for coll in resolved.collections] == [
        "surface",
        "surface2",
        "border1",
        "border2",
        "NotatÅ",
        "border4",
    ]


def test_feature_model_and_processes_resolve():
    cad = next(d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "cadastre")
    assert cad.processes == ("hello",)
    by_name = {c.name: c for c in cad.collections}
    assert by_name["parcels"].feature_model == "simple"
    assert by_name["parcels"].supports_crud is True
    assert by_name["blocks"].feature_model == "topology"
    assert by_name["blocks"].supports_crud is False


def test_fkb_bane_dataset_resolves_expected_geometry_and_upsert_field():
    fkb_bane = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "fkb_bane"
    )
    assert [coll.name for coll in fkb_bane.collections] == [
        "jernbaneplattformkant",
        "spormidt",
    ]
    assert fkb_bane.srid == 5973

    for coll in fkb_bane.collections:
        assert coll.geometry_type == "MultiLineString"
        assert coll.has_z is True
        assert coll.upsert_field == "identifikasjon.lokalid"
        assert coll.upsert_path == "identifikasjon.lokalid"
        assert coll.supports_upsert


def test_bygning_dataset_resolves_expected_geometry_and_upsert_field():
    bygning = next(
        d for d in load_resolved_datasets(DESCRIPTIONS) if d.name == "bygning"
    )
    assert [coll.name for coll in bygning.collections] == [
        "bygning",
        "bygning_omrade",
        "bygning_senterlinje",
        "bygning_posisjon",
    ]
    assert bygning.srid == 5972

    linework = next(coll for coll in bygning.collections if coll.name == "bygning")
    assert linework.geometry_type == "MultiLineString"
    assert linework.has_z is True
    assert linework.upsert_field == "lokalid"
    assert linework.upsert_path == "lokalid"
    assert linework.supports_upsert

    area = next(coll for coll in bygning.collections if coll.name == "bygning_omrade")
    assert area.geometry_type == "MultiPolygon"
    assert area.has_z is True
    assert area.upsert_field == "lokalid"
    assert area.upsert_path == "lokalid"
    assert area.supports_upsert

    centerline = next(
        coll for coll in bygning.collections if coll.name == "bygning_senterlinje"
    )
    assert centerline.geometry_type == "MultiLineString"
    assert centerline.has_z is True
    assert centerline.upsert_field == "lokalid"
    assert centerline.upsert_path == "lokalid"
    assert centerline.supports_upsert

    position = next(
        coll for coll in bygning.collections if coll.name == "bygning_posisjon"
    )
    assert position.geometry_type == "Point"
    assert position.has_z is True
    assert position.upsert_field == "lokalid"
    assert position.upsert_path == "lokalid"
    assert position.supports_upsert


def test_unknown_process_raises_clear_error():
    dataset = DatasetDef.model_validate(
        {"name": "x", "srid": 4326, "processes": ["nope"]}
    )
    with pytest.raises(DescriptionError, match="unknown process"):
        resolve_dataset(dataset)


# --------------------------------------------------------------------------
# Names in dataset descriptions
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_name",
    [
        "fkb-bane",  # hyphen (reviewer's flagship example)
        "FKB Bane",  # spaces
        "éclair",  # letters outside the supported Norwegian set
        "1cadastre",  # leading digit
        "",  # empty
        "a" * 41,  # over 40 bytes
        "æ" * 21,  # 42 UTF-8 bytes
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
        RelationshipDef.model_validate({"property": "r", "target": "fkb-bane"})


@pytest.mark.parametrize(
    "good_name",
    [
        "a",
        "_x",
        "cadastre",
        "arealressurs_grense",
        "ArealressursGrense",
        "datafangstmetodeHøyde",
        "ÆØÅ",
        "æ" * 20,  # 40 UTF-8 bytes
        "a" * 40,
    ],
)
def test_legal_name_preserves_original_spelling(good_name):
    ds = DatasetDef.model_validate({"name": good_name, "srid": 4326})
    assert ds.name == good_name


def test_legal_name_propagates_through_nested_models():
    """The constraint must apply to nested lists of models: a bad ``FieldDef``
    name inside an otherwise valid dataset should be caught at the outer
    parse, not silently accepted."""
    with pytest.raises(ValidationError):
        DatasetDef.model_validate(
            {
                "name": "ok",
                "srid": 4326,
                "collections": [
                    {
                        "name": "ok_coll",
                        "fields": [{"name": "bad-field", "type": "string"}],
                    }
                ],
            }
        )


def test_legal_name_surfaces_via_file_loader(tmp_path):
    """The constraint must fire via the file-loading path, not just via direct
    ``model_validate``. ``load_dataset`` wraps ``ValidationError`` as
    ``DescriptionError``."""
    p = tmp_path / "d.yaml"
    p.write_text("name: fkb-bane\ncollections: []\n", encoding="utf-8")
    with pytest.raises(DescriptionError):
        load_dataset(p)


def test_fields_differing_only_in_case_are_rejected(simple_description):
    fields = simple_description["collections"][1]["fields"]
    fields.append({"name": "FELTø", "type": "string"})
    with pytest.raises(ValidationError, match="conflict"):
        DatasetDef.model_validate(simple_description)


def test_nested_fields_differing_only_in_case_are_rejected(simple_description):
    fields = simple_description["collections"][1]["fields"][1]["fields"]
    fields.append({"name": "VERDIå", "type": "integer"})
    with pytest.raises(ValidationError, match="conflict"):
        DatasetDef.model_validate(simple_description)


def test_same_nested_field_name_is_allowed_in_different_objects(simple_description):
    fields = simple_description["collections"][1]["fields"]
    fields.append(
        {
            "name": "andreEgenskaper",
            "type": "object",
            "fields": [{"name": "verdiÅ", "type": "integer"}],
        }
    )
    assert len(DatasetDef.model_validate(simple_description).collections[1].fields) == 3


def test_collection_and_process_names_share_the_api_namespace(simple_description):
    simple_description["processes"].append("hello")
    simple_description["collections"].append({"name": "Hello"})
    with pytest.raises(ValidationError, match="conflict"):
        DatasetDef.model_validate(simple_description)


def test_collection_names_differing_only_in_case_are_rejected(simple_description):
    simple_description["collections"].append({"name": "nårwegiænøbject"})
    with pytest.raises(ValidationError, match="conflict"):
        DatasetDef.model_validate(simple_description)


def test_generated_names_are_reserved_ignoring_case(simple_description):
    simple_description["name"] = "OGC"
    with pytest.raises(DescriptionError, match="reserved"):
        resolve_dataset(DatasetDef.model_validate(simple_description))
    simple_description["name"] = "EksempelDatasett"
    simple_description["collections"][1]["name"] = "Association"
    with pytest.raises(DescriptionError, match="reserved"):
        resolve_dataset(DatasetDef.model_validate(simple_description))


def test_dataset_names_are_unique_across_files_ignoring_case(tmp_path):
    (tmp_path / "a.yaml").write_text("name: Example\nsrid: 4326\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("name: example\nsrid: 4326\n", encoding="utf-8")
    with pytest.raises(DescriptionError, match="conflict"):
        load_resolved_datasets(tmp_path)


# --------------------------------------------------------------------------
# Nested object fields
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
    return DatasetDef.model_validate({"name": "x", "srid": 4326, "collections": [coll]})


def test_object_field_resolves_to_jsonb_with_sub_fields():
    ds = resolve_dataset(_dataset_with_object_field())
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
            "srid": 4326,
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
    ds = resolve_dataset(dataset)
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
            "srid": 4326,
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
    ds = resolve_dataset(dataset)
    medium = ds.collections[0].fields[0]
    assert medium.enum == ("T", "U", "V")


def test_indexable_propagates_to_resolved_field():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
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
    ds = resolve_dataset(dataset)
    assert ds.collections[0].fields[0].indexable is True


def test_error_message_contains_full_path_for_nested_bad_type():
    """Resolution errors name the full sub-field path."""
    dataset = DatasetDef.model_validate(
        {
            "name": "myds",
            "srid": 4326,
            "collections": [
                {
                    "name": "mycoll",
                    "fields": [
                        {
                            "name": "kvalitet",
                            "type": "object",
                            "fields": [{"name": "method", "type": "no_such_type"}],
                        }
                    ],
                }
            ],
        }
    )
    with pytest.raises(DescriptionError, match="kvalitet"):
        resolve_dataset(dataset)


def test_outward_identifier_dot_path_validated_against_fields():
    """An outward_identifier referencing a non-existent sub-field must raise."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
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
        resolve_dataset(dataset)


def test_server_managed_dot_path_validated_against_fields():
    """A server_managed path referencing a non-existent field must raise."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
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
        resolve_dataset(dataset)


def test_outward_identifier_and_server_managed_stored_on_resolved_collection():
    """Valid declarations must propagate to the resolved collection."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
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
    ds = resolve_dataset(dataset)
    coll = ds.collections[0]
    assert coll.outward_identifier_path == "identifikasjon.lokalid"
    assert coll.server_managed_paths["identifikasjon.versjonid"] == "timestamp_iso"


# --------------------------------------------------------------------------
# Loader post-code suspects
# --------------------------------------------------------------------------


def test_codelist_resolves():
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
            "codelists": [{"name": "medium", "values": [{"code": "T"}]}],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "medium"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset)
    assert ds.collections[0].fields[0].codelist == "medium"


# --------------------------------------------------------------------------
# FieldDef: exactly one of type / codelist
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "fld",
    [
        {"name": "f", "type": "string", "codelist": "c"},
    ],
)
def test_field_rejects_multiple_type_sources(fld):
    """Reject ambiguous type declarations before resolving fields."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate(fld)


def test_field_rejects_no_type_source():
    """A field must select its column type somehow."""
    with pytest.raises(ValidationError):
        FieldDef.model_validate({"name": "f"})


# --------------------------------------------------------------------------
# codelist_values flow
# --------------------------------------------------------------------------


def test_codelist_values_populated_from_declared_codes():
    """Suspect: codes in ResolvedField.codelist_values must match the codelist
    declaration order and content."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
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
    ds = resolve_dataset(dataset)
    assert ds.collections[0].fields[0].codelist_values == ("ASFALT", "GRUS", "STEIN")


def test_codelist_with_no_values_gives_empty_codelist_values():
    """Suspect: a codelist with no declared values must not raise; codelist_values
    must be an empty tuple so downstream callers can check truthiness safely."""
    dataset = DatasetDef.model_validate(
        {
            "name": "x",
            "srid": 4326,
            "codelists": [{"name": "empty"}],
            "collections": [
                {"name": "c", "fields": [{"name": "f", "codelist": "empty"}]}
            ],
        }
    )
    ds = resolve_dataset(dataset)
    assert ds.collections[0].fields[0].codelist_values == ()
