from __future__ import annotations

import psycopg
import pytest
from fixtures.footprint_cases import CASES, Case
from psycopg import sql

from geocomponents.schema import functions

FOOTPRINT_SCHEMA = "topogdb"


def _build_footprint(lines: str | None, expected_footprint: str | None):
    return (
        sql.SQL(
            """
with input(lines) as (
    select case
        when %(lines)s::text is null then null::geometry
        else ST_GeomFromText(%(lines)s::text)
    end
)
select
    (facts).footprint is null as footprint_is_null,
    case
        when %(expected_footprint)s::text is null then (facts).footprint is null
        else ST_Equals((facts).footprint, ST_GeomFromText(%(expected_footprint)s::text))
    end as footprint_matches,
    ST_AsText((facts).footprint) as actual_footprint,
    (facts).areas,
    (facts).holes,
    (facts).curves_all_used
from (
    select {}.build_footprint(lines) as facts
    from input
) built
"""
        ).format(sql.Identifier(FOOTPRINT_SCHEMA)),
        {"lines": lines, "expected_footprint": expected_footprint},
    )


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_build_footprint_cases(conn, case: Case):
    query, params = _build_footprint(case.lines, case.footprint_facts.footprint)
    row = conn.execute(query, params).fetchone()

    assert row is not None
    (
        footprint_is_null,
        footprint_matches,
        actual_footprint,
        areas,
        holes,
        curves_all_used,
    ) = row
    assert footprint_is_null is (case.footprint_facts.footprint is None)
    assert footprint_matches, (
        case.id,
        actual_footprint,
        case.footprint_facts.footprint,
    )
    assert areas == case.footprint_facts.areas
    assert holes == case.footprint_facts.holes
    assert curves_all_used is case.footprint_facts.curves_all_used


@pytest.mark.parametrize(
    "wkt",
    [
        "POINT(0 0)",
        "POLYGON((0 0,20 0,20 20,0 20,0 0))",
        "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
        "GEOMETRYCOLLECTION(LINESTRING(0 0,20 0),LINESTRING(20 0,20 20))",
        "MULTILINESTRING((0 0,20 0),(20 0,20 20),(20 20,0 20),(0 20,0 0),EMPTY)",
    ],
)
def test_build_footprint_rejects_non_multilinestring_input(conn, wkt):
    with pytest.raises(psycopg.errors.InternalError_):
        conn.execute(
            sql.SQL("select {}.build_footprint(ST_GeomFromText(%s))").format(
                sql.Identifier(FOOTPRINT_SCHEMA)
            ),
            (wkt,),
        ).fetchone()


def test_build_footprint_drops_z_before_noding(conn):
    mixed_z = next(case for case in CASES if case.id == "square-mixed-z-valid")
    row = conn.execute(
        sql.SQL(
            """
with input(lines) as (
    select ST_GeomFromText(%(lines)s::text)
)
select ST_Zmflag(({}.build_footprint(lines)).footprint) as zmflag
from input
"""
        ).format(sql.Identifier(FOOTPRINT_SCHEMA)),
        {"lines": mixed_z.lines},
    ).fetchone()

    assert row is not None
    assert row[0] == 0


def test_apply_topogdb_is_idempotent(db):
    with psycopg.connect(db) as conn:
        functions.apply_topogdb(conn)
        functions.apply_topogdb(conn)
        row = conn.execute(
            sql.SQL(
                "select ({}.build_footprint(null::geometry)).footprint is null"
            ).format(sql.Identifier(FOOTPRINT_SCHEMA))
        ).fetchone()

    assert row is not None
    assert row[0] is True
