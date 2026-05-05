"""
Unit tests for FKB-Bane Pydantic models and code list enums.

Run with:
    python -m unittest tests.test_models
"""

import unittest

from pydantic import ValidationError

from app.models.fkb_bane import (
    Datafangstmetode,
    Hoydereferanse,
    Identifikasjon,
    JernbaneplattformkantProperties,
    Jernbanetype,
    Medium,
    Posisjonskvalitet,
    SpormidtProperties,
)
from app.models.fkb_felles import Synbarhet

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

IDENTIFIKASJON_DATA = {
    "lokalId": "abc123",
    "navnerom": "no.kartverket.fkb.bane",
}

KVALITET_DATA = {
    "datafangstmetode": "fot",
}

JERNBANEPLATTFORMKANT_DATA = {
    "identifikasjon": IDENTIFIKASJON_DATA,
    "datafangstdato": "2022-05-01",
    "oppdateringsdato": "2023-01-15T10:00:00+00:00",
    "kvalitet": KVALITET_DATA,
    "medium": "T",
}

SPORMIDT_DATA = {
    **JERNBANEPLATTFORMKANT_DATA,
    "jernbanetype": "J",
    "høydereferanse": "topp",
}


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestMedium(unittest.TestCase):
    def test_exact_value(self):
        self.assertEqual(Medium("T"), Medium.T)

    def test_lowercase(self):
        self.assertEqual(Medium("t"), Medium.T)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            Medium("Z")


class TestJernbanetype(unittest.TestCase):
    def test_exact_value(self):
        self.assertEqual(Jernbanetype("J"), Jernbanetype.J)

    def test_lowercase(self):
        self.assertEqual(Jernbanetype("j"), Jernbanetype.J)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            Jernbanetype("X")


class TestHoydereferanse(unittest.TestCase):
    def test_exact_value(self):
        self.assertEqual(Hoydereferanse("Topp"), Hoydereferanse.topp)

    def test_mixed_case(self):
        self.assertEqual(Hoydereferanse("fOt"), Hoydereferanse.fot)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            Hoydereferanse("Midt")


class TestDatafangstmetode(unittest.TestCase):
    def test_exact_value(self):
        self.assertEqual(Datafangstmetode("fot"), Datafangstmetode.fot)

    def test_mixed_case(self):
        self.assertEqual(Datafangstmetode("FoT"), Datafangstmetode.fot)

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            Datafangstmetode("xyz")


class TestSynbarhet(unittest.TestCase):
    def test_valid_values(self):
        for i in range(4):
            Synbarhet(str(i))  # Asserts no error

    def test_invalid_values(self):
        for i in (-1, 4):
            with self.assertRaises(ValueError):
                Synbarhet(i)


# ---------------------------------------------------------------------------
# Identifikasjon tests
# ---------------------------------------------------------------------------


class TestIdentifikasjon(unittest.TestCase):
    def test_from_camel_case_alias(self):
        m = Identifikasjon.model_validate(IDENTIFIKASJON_DATA)
        self.assertEqual(m.lokal_id, "abc123")
        self.assertEqual(m.navnerom, "no.kartverket.fkb.bane")

    def test_from_python_field_name(self):
        m = Identifikasjon(lokal_id="abc123", navnerom="no.kartverket.fkb.bane")
        self.assertEqual(m.lokal_id, "abc123")

    def test_versjon_id_optional(self):
        m = Identifikasjon.model_validate(IDENTIFIKASJON_DATA)
        self.assertIsNone(m.versjon_id)

    def test_versjon_id_set(self):
        data = {**IDENTIFIKASJON_DATA, "versjonId": "1.0"}
        m = Identifikasjon.model_validate(data)
        self.assertEqual(m.versjon_id, "1.0")

    def test_missing_required_field_raises(self):
        with self.assertRaises(ValidationError):
            Identifikasjon.model_validate({"lokalId": "abc123"})  # navnerom missing


# ---------------------------------------------------------------------------
# Posisjonskvalitet tests
# ---------------------------------------------------------------------------


class TestPosisjonskvalitet(unittest.TestCase):
    def test_minimal(self):
        m = Posisjonskvalitet.model_validate(KVALITET_DATA)
        self.assertEqual(m.datafangstmetode, Datafangstmetode.fot)
        self.assertIsNone(m.noyaktighet)
        self.assertIsNone(m.synbarhet)

    def test_with_noyaktighet(self):
        posisjonskvalitet = Posisjonskvalitet(nøyaktighet=2, datafangstmetode="dig")
        self.assertEqual(2, posisjonskvalitet.noyaktighet)

    def test_missing_datafangstmetode_raises(self):
        with self.assertRaises(ValidationError):
            Posisjonskvalitet.model_validate({})


# ---------------------------------------------------------------------------
# Jernbaneplattformkant tests
# ---------------------------------------------------------------------------


class TestJernbaneplattformkant(unittest.TestCase):
    def test_valid(self):
        m = JernbaneplattformkantProperties.model_validate(JERNBANEPLATTFORMKANT_DATA)
        self.assertEqual(m.medium, Medium.T)
        self.assertIsInstance(m.identifikasjon, Identifikasjon)
        self.assertIsInstance(m.kvalitet, Posisjonskvalitet)

    def test_optional_fields_default_none(self):
        m = JernbaneplattformkantProperties.model_validate(JERNBANEPLATTFORMKANT_DATA)
        self.assertIsNone(m.sluttdato)
        self.assertIsNone(m.verifiseringsdato)
        self.assertIsNone(m.informasjon)
        self.assertIsNone(m.eksternpeker)

    def test_missing_required_field_raises(self):
        jernbane_missing_medium = JERNBANEPLATTFORMKANT_DATA.copy()
        del jernbane_missing_medium["medium"]
        with self.assertRaises(ValidationError):
            JernbaneplattformkantProperties.model_validate(jernbane_missing_medium)


# ---------------------------------------------------------------------------
# Spormidt tests
# ---------------------------------------------------------------------------


class TestSpormidt(unittest.TestCase):
    def test_valid(self):
        m = SpormidtProperties.model_validate(SPORMIDT_DATA)
        self.assertEqual(m.jernbanetype, Jernbanetype.J)
        self.assertEqual(m.hoydereferanse, Hoydereferanse.topp)

    def test_inherits_jernbaneplattformkant_fields(self):
        m = SpormidtProperties.model_validate(SPORMIDT_DATA)
        self.assertEqual(m.medium, Medium.T)
        self.assertIsInstance(m.identifikasjon, Identifikasjon)

    def test_hoydereferanse_alias(self):
        spormidt = SpormidtProperties(**SPORMIDT_DATA)
        self.assertEqual(SPORMIDT_DATA["høydereferanse"], spormidt.hoydereferanse)

    def test_without_hoydereferanse_alias(self):
        spormidt_data_without_alias = SPORMIDT_DATA.copy()
        spormidt_data_without_alias["hoydereferanse"] = spormidt_data_without_alias.pop(
            "høydereferanse"
        )
        spormidt = SpormidtProperties(**spormidt_data_without_alias)
        self.assertEqual(SPORMIDT_DATA["høydereferanse"], spormidt.hoydereferanse)

    def test_missing_jernbanetype_raises(self):
        data = {**JERNBANEPLATTFORMKANT_DATA}  # no jernbanetype
        with self.assertRaises(ValidationError):
            SpormidtProperties.model_validate(data)


if __name__ == "__main__":
    unittest.main()
