"""Cases for topogdb.build_footprint.

Shapes use a 20x20 outer square and a 20x20 outer square with a 10x10 hole.
"""

from __future__ import annotations

from dataclasses import dataclass

SQUARE = "POLYGON((0 0,20 0,20 20,0 20,0 0))"
SQUARE_WITH_COURTYARD = "POLYGON((0 0,20 0,20 20,0 20,0 0),(5 5,15 5,15 15,5 15,5 5))"


@dataclass(frozen=True)
class FootprintFacts:
    footprint: str | None
    sections_doubled: float
    areas: int
    holes: int
    curves_all_used: bool


@dataclass(frozen=True)
class Case:
    id: str
    curves: list[str] | None  # None -> SQL NULL
    footprint_facts: FootprintFacts


CASES = [
    # 1
    Case(
        "square-from-single-curve",
        ["LINESTRING(0 0,20 0,20 20,0 20,0 0)"],
        FootprintFacts(SQUARE, 0, 1, 0, True),
    ),
    # 2
    Case(
        "square-from-four-curves",
        [
            "LINESTRING(0 0,20 0)",
            "LINESTRING(20 0,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, True),
    ),
    # 3. Same lines as 2 scrambled
    Case(
        "square from scrambled curves",
        [
            "LINESTRING(20 0,20 20)",
            "LINESTRING(0 20,0 0)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 0,20 0)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, True),
    ),
    # 4. same as 2 with first line reversed
    Case(
        "square-mixed-direction",
        [
            "LINESTRING(20 0,0 0)",
            "LINESTRING(20 0,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, True),
    ),
    # 5. Non closed small gap
    Case(
        "square-nonclosed",
        [
            "LINESTRING(0 0,20 0)",
            "LINESTRING(20 0.001,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(None, 0, 0, 0, False),
    ),
    # 6.
    Case(
        "square-mixed-z-valid",
        [
            "LINESTRING Z(0 0 10,20 0 11)",
            "LINESTRING Z(20 0 21,20 20 22)",
            "LINESTRING Z(20 20 31,0 20 32)",
            "LINESTRING Z(0 20 41,0 0 42)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, True),
    ),
    # 7. ?
    Case(
        "bowtie",
        [
            "LINESTRING(0 0,20 20)",
            "LINESTRING(20 20,20 0)",
            "LINESTRING(20 0,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(
            "MULTIPOLYGON(((10 10,0 0,0 20,10 10)),((20 20,20 0,10 10,20 20)))",
            0,
            2,
            0,
            True,
        ),
    ),
    # 8.
    Case(
        "one-span-drawn-twice",
        [
            "LINESTRING(0 0,20 0)",
            "LINESTRING(0 0,20 0)",
            "LINESTRING(20 0,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(SQUARE, 20.0, 1, 0, True),
    ),
    # 9.
    Case(
        "bottom-edge-overshoots-corner",
        [
            "LINESTRING(0 0,30 0)",
            "LINESTRING(20 0,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, False),
    ),
    # 10.
    Case(
        "spur-attached-at-a-shared-corner",
        [
            "LINESTRING(0 0,20 0)",
            "LINESTRING(20 0,20 20)",
            "LINESTRING(20 20,0 20)",
            "LINESTRING(0 20,0 0)",
            "LINESTRING(20 0,30 0)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, False),
    ),
    # 11.
    Case(
        "two-separate-squares",
        [
            "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
            "LINESTRING(30 0,40 0,40 10,30 10,30 0)",
        ],
        FootprintFacts(
            "MULTIPOLYGON(((0 0,20 0,20 20,0 20,0 0)),((30 0,40 0,40 10,30 10,30 0)))",
            0,
            2,
            0,
            True,
        ),
    ),
    # 12.
    Case(
        "second-nonclosed",
        ["LINESTRING(0 0,20 0,20 20,0 20, 0 0)", "LINESTRING(30 0, 40 0,40 10)"],
        FootprintFacts(SQUARE, 0, 1, 0, False),
    ),
    # 13.
    Case("null-input", None, FootprintFacts(None, 0, 0, 0, False)),
    # 14.
    Case(
        "empty-input",
        ["LINESTRING EMPTY"],
        FootprintFacts("POLYGON EMPTY", 0, 0, 0, False),
    ),
    # 15.
    Case(
        "courtyard-both-rings-closed",
        ["LINESTRING(0 0,20 0,20 20,0 20,0 0)", "LINESTRING(5 5,15 5,15 15,5 15,5 5)"],
        FootprintFacts(SQUARE_WITH_COURTYARD, 0, 1, 1, True),
    ),
    # 16.
    Case(
        "courtyard-inner-ring-open",
        [
            "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
            "LINESTRING(5 5,15 5)",
            "LINESTRING(15 5,15 15)",
            "LINESTRING(15 15,5 15)",
        ],
        FootprintFacts(SQUARE, 0, 1, 0, False),
    ),
    # 17.
    Case(
        "courtyard-ring-shares-edge",
        ["LINESTRING(0 0,20 0,20 20,0 20,0 0)", "LINESTRING(0 5,10 5,10 15,0 15,0 5)"],
        FootprintFacts(SQUARE, 10.0, 1, 0, False),
    ),
    # 18.
    Case(
        "courtyard-ring-attached",
        ["LINESTRING(0 0,20 0,20 20, 0 20,0 0)", "LINESTRING(0 5,10 5,10 15,0 15)"],
        FootprintFacts(SQUARE, 0, 1, 0, False),
    ),
    # 19.
    Case(
        "courtyard-ring-crosses-outer",
        [
            "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
            "LINESTRING(-5 5,10 5,10 15,-5 15,-5 5)",
        ],
        FootprintFacts(
            "POLYGON((-5 5,-5 15,0 15,0 20,20 20,20 0,0 0,0 5,-5 5))",
            0,
            1,
            0,
            False,
        ),
    ),
    # 20.
    Case(
        "closed-island-inside-the-courtyard",
        [
            "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
            "LINESTRING(5 5,15 5,15 15,5 15,5 5)",
            "LINESTRING(8 8,12 8,12 12,8 12,8 8)",
        ],
        FootprintFacts(
            "MULTIPOLYGON(((0 0,20 0,20 20,0 20,0 0),"
            "(5 5,15 5,15 15,5 15,5 5)),((8 8,12 8,12 12,8 12,8 8)))",
            0,
            2,
            1,
            True,
        ),
    ),
    # 21.
    Case(
        "open-island-inside-the-courtyard",
        [
            "LINESTRING(0 0,20 0,20 20,0 20,0 0)",
            "LINESTRING(5 5,15 5,15 15,5 15,5 5)",
            "LINESTRING(8 8,12 8,12 12)",
        ],
        FootprintFacts(SQUARE_WITH_COURTYARD, 0, 1, 1, False),
    ),
]
