from __future__ import annotations

import runpy
from pathlib import Path

import psycopg
import pytest
from psycopg import sql

from geocomponents.schema import functions

FOOTPRINT_SCHEMA = "topogdb"

CASES = runpy.run_path(str(Path(__file__).parent / "fixtures" / "footprint_cases.py"))[
    "CASES"
]


def _build_footprint(curves: list[str] | None):
    return (
        sql.SQL(
            """
with input(lines) as (
    select case
        when %(curves)s::text[] is null then null::geometry
        else (
            select ST_Collect(ST_GeomFromText(curve))
            from unnest(%(curves)s::text[]) as curve
        )
    end
)
select
    (facts).footprint is null as footprint_is_null,
    case
        when %(expected_footprint)s::text is null then (facts).footprint is null
        else ST_Equals((facts).footprint, ST_GeomFromText(%(expected_footprint)s::text))
    end as footprint_matches,
    ST_AsText((facts).footprint) as actual_footprint,
    (facts).sections_doubled,
    (facts).areas,
    (facts).holes,
    (facts).curves_all_used
from (
    select {}.build_footprint(lines) as facts
    from input
) built
"""
        ).format(sql.Identifier(FOOTPRINT_SCHEMA)),
        {"curves": curves},
    )


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_build_footprint_cases(conn, case):
    sql, params = _build_footprint(case.curves)
    params["expected_footprint"] = case.footprint_facts.footprint
    row = conn.execute(sql, params).fetchone()

    assert row is not None
    (
        footprint_is_null,
        footprint_matches,
        actual_footprint,
        sections_doubled,
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
    assert sections_doubled == case.footprint_facts.sections_doubled
    assert areas == case.footprint_facts.areas
    assert holes == case.footprint_facts.holes
    assert curves_all_used is case.footprint_facts.curves_all_used


def test_build_footprint_drops_z_before_noding(conn):
    mixed_z = next(case for case in CASES if case.id == "square-mixed-z-valid")
    row = conn.execute(
        sql.SQL(
            """
with input(lines) as (
    select (
        select ST_Collect(ST_GeomFromText(curve))
        from unnest(%(curves)s::text[]) as curve
    )
)
select ST_Zmflag(({}.build_footprint(lines)).footprint) as zmflag
from input
"""
        ).format(sql.Identifier(FOOTPRINT_SCHEMA)),
        {"curves": mixed_z.curves},
    ).fetchone()

    assert row is not None
    assert row[0] == 0


def test_apply_topogdb_is_idempotent(db):
    with psycopg.connect(db) as conn:
        functions.apply_topogdb(conn)
        functions.apply_topogdb(conn)
