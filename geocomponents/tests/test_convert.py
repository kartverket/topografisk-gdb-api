"""Pre-code and post-code suspect tests for the QMS converter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from geocomponents.convert import _safe_id, convert_qms
from geocomponents.descriptions.loader import resolve_dataset
from geocomponents.descriptions.models import Commons, DatasetDef

QMS_FILE = Path(__file__).resolve().parents[2] / "UML-schemas" / "FKBBane_50_qms.json"


@pytest.fixture(scope="module")
def qms_data():
    return json.loads(QMS_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def converted(qms_data):
    from geocomponents.convert import convert_qms

    return yaml.safe_load(convert_qms(qms_data, "fkb_bane", 4326, True))


# --------------------------------------------------------------------------
# _safe_id: Norwegian character transliteration
# --------------------------------------------------------------------------


def test_safe_id_transliterates_o_with_stroke():
    """Pre-code suspect: ø must become 'o' so the name passes SafeIdentifier."""

    assert _safe_id("nøyaktighet") == "noyaktighet"


def test_safe_id_transliterates_capital_o_with_stroke_and_lowercases():
    """Pre-code suspect: Ø must become 'o' (lowercase after transliteration)."""

    assert _safe_id("datafangstmetodeHøyde") == "datafangstmetodehoyde"
    assert _safe_id("høydereferanse") == "hoydereferanse"


# --------------------------------------------------------------------------
# Collection structure
# --------------------------------------------------------------------------


def test_convert_produces_two_collections(converted):
    """Pre-code suspect: FKB-Bane has two FeatureTypes — output must have two
    collections with the expected transliterated names."""
    assert len(converted["collections"]) == 2
    names = {c["name"] for c in converted["collections"]}
    assert "jernbaneplattformkant" in names
    assert "spormidt" in names


# --------------------------------------------------------------------------
# FKB Identifikasjon conventions
# --------------------------------------------------------------------------


def test_identifikasjon_struct_sets_outward_identifier(converted):
    """Pre-code suspect: a Struct with DAT TypeName 'Identifikasjon' must set
    outward_identifier to '<field_name>.lokalid' on the collection."""
    coll = next(
        c for c in converted["collections"] if c["name"] == "jernbaneplattformkant"
    )
    assert coll.get("outward_identifier") == "identifikasjon.lokalid"


def test_identifikasjon_struct_sets_server_managed_versjonid(converted):
    """Pre-code suspect: versjonId inside Identifikasjon must be timestamp_iso
    in server_managed."""
    coll = next(
        c for c in converted["collections"] if c["name"] == "jernbaneplattformkant"
    )
    sm = coll.get("server_managed", {})
    assert sm.get("identifikasjon.versjonid") == "timestamp_iso"


def test_oppdateringsdato_in_server_managed_and_in_fields(converted):
    """Pre-code suspect: oppdateringsdato is server-managed AND still emitted
    as a regular field (the column must exist in the DB)."""
    coll = next(
        c for c in converted["collections"] if c["name"] == "jernbaneplattformkant"
    )
    sm = coll.get("server_managed", {})
    assert sm.get("oppdateringsdato") == "timestamp_iso"
    field_names = {f["name"] for f in coll["fields"]}
    assert "oppdateringsdato" in field_names


# --------------------------------------------------------------------------
# CodeList handling
# --------------------------------------------------------------------------


def test_medium_field_uses_dataset_codelist_with_correct_values(converted):
    """Pre-code suspect: a CodeList attribute must reference a named dataset-level
    codelist, and that codelist must carry the code values from DefaultAttributeTypes."""
    coll = next(
        c for c in converted["collections"] if c["name"] == "jernbaneplattformkant"
    )
    medium_fld = next(f for f in coll["fields"] if f["name"] == "medium")
    assert "codelist" in medium_fld
    cl_name = medium_fld["codelist"]
    cl = next((c for c in converted["codelists"] if c["name"] == cl_name), None)
    assert cl is not None
    codes = {v["code"] for v in cl["values"]}
    assert "T" in codes  # På terrenget value


def test_shared_codelist_not_duplicated(converted):
    """Post-code suspect: datafangstmetode appears in both top-level and as a
    Struct sub-field (via datafangstmetodeHøyde with same TypeName) — must
    produce only one codelist with that name, not two."""
    names = [c["name"] for c in converted["codelists"]]
    assert len(names) == len(set(names)), "duplicate codelist names found"


# --------------------------------------------------------------------------
# Full validation via geocomponents loader
# --------------------------------------------------------------------------


def test_convert_output_validates_as_geocomponents_dataset(qms_data):
    """Pre-code suspect (integration): the YAML must parse and resolve without
    error through the full description pipeline."""

    yaml_str = convert_qms(qms_data, "fkb_bane", 4326, True)
    dataset = DatasetDef.model_validate(yaml.safe_load(yaml_str))
    resolved = resolve_dataset(dataset, Commons())
    assert len(resolved.collections) == 2
