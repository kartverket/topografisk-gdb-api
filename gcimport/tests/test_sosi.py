from __future__ import annotations

from pathlib import Path

import pytest

from gcimport.parsers.sosi import (
    SosiCoordinate,
    SosiInlineAttribute,
    SosiNode,
    SosiParseError,
    parse_file,
    parse_text,
    summarize_tree,
)


def test_parse_text_builds_tree_for_header_points_curves_and_areas() -> None:
    document = parse_text(
        """
.HODE
..TEGNSETT UTF-8
..TRANSPAR
...KOORDSYS 22
.PUNKT 1:
..OBJTYPE Bygning
..NØ
68530635600 5295421498
.KURVE 27090:
..OBJTYPE Takkant
..KVALITET
...DATAFANGSTMETODE fot
..IDENT
...LOKALID d45fd8a8-a184-43a9-a82a-188b78d0543a
..NØH
68530793009 5295402541 4956520 ...KP 1
..NØH
68530735036 5295419734 4956520
68530748313 5295464499 4956520
68530806285 5295447306 4956520
68530793009 5295402541 4956520 ...KP 1
.FLATE 72639:
..OBJTYPE AnnenBygning
..REF :-27090
..NØ
68530770661 5295433520
        """.strip()
    )

    assert document.header is not None
    assert document.header.name == "HODE"
    assert [
        child.name for child in document.header.children if isinstance(child, SosiNode)
    ] == [
        "TEGNSETT",
        "TRANSPAR",
    ]

    transpar = document.header.children[1]
    assert isinstance(transpar, SosiNode)
    assert transpar.children == [SosiNode(name="KOORDSYS", value="22", source_line=4)]

    assert [child.name for child in document.children] == ["PUNKT", "KURVE", "FLATE"]

    point = document.children[0]
    assert point.value == "1"
    assert [child.name for child in point.children if isinstance(child, SosiNode)] == [
        "OBJTYPE",
        "NØ",
    ]
    assert point.children[1].children == [
        SosiCoordinate(values=(68530635600, 5295421498), source_line=8)
    ]

    curve = document.children[1]
    assert curve.value == "27090"
    assert [child.name for child in curve.children if isinstance(child, SosiNode)] == [
        "OBJTYPE",
        "KVALITET",
        "IDENT",
        "NØH",
        "NØH",
    ]

    quality = curve.children[1]
    assert isinstance(quality, SosiNode)
    assert quality.children == [
        SosiNode(name="DATAFANGSTMETODE", value="fot", source_line=12)
    ]

    first_ring = curve.children[3]
    assert isinstance(first_ring, SosiNode)
    assert first_ring.name == "NØH"
    assert first_ring.children == [
        SosiCoordinate(
            values=(68530793009, 5295402541, 4956520),
            attributes=[SosiInlineAttribute(name="KP", value="1")],
            source_line=16,
        )
    ]

    second_ring = curve.children[4]
    assert isinstance(second_ring, SosiNode)
    assert [coordinate.values for coordinate in second_ring.children] == [
        (68530735036, 5295419734, 4956520),
        (68530748313, 5295464499, 4956520),
        (68530806285, 5295447306, 4956520),
        (68530793009, 5295402541, 4956520),
    ]
    assert second_ring.children[-1].attributes == [
        SosiInlineAttribute(name="KP", value="1")
    ]

    area = document.children[2]
    assert area.value == "72639"
    assert area.children[1] == SosiNode(name="REF", value=":-27090", source_line=24)
    assert area.children[2].children == [
        SosiCoordinate(values=(68530770661, 5295433520), source_line=26)
    ]


def test_parse_file_reads_utf8_sosi_documents(tmp_path: Path) -> None:
    path = tmp_path / "sample.sos"
    path.write_text(".FLATE 1:\n..OBJTYPE AnnenBygning\n", encoding="utf-8")

    document = parse_file(path)

    assert document.children == [
        SosiNode(
            name="FLATE",
            value="1",
            children=[SosiNode(name="OBJTYPE", value="AnnenBygning", source_line=2)],
            source_line=1,
        )
    ]


def test_parse_text_rejects_coordinate_records_without_parent_key() -> None:
    with pytest.raises(
        SosiParseError,
        match="coordinate record without a parent key",
    ):
        parse_text("68530793009 5295402541 4956520")


def test_parse_text_rejects_invalid_depth_jumps() -> None:
    with pytest.raises(SosiParseError, match="invalid nesting depth 2"):
        parse_text("..OBJTYPE Takkant")


def test_summarize_tree_counts_objects_objtypes_and_kp_markers() -> None:
    document = parse_text(
        """
.HODE
..TEGNSETT UTF-8
.PUNKT 0:
..OBJTYPE Bygning
..NØ
7 8
.KURVE 1:
..OBJTYPE Takkant
..NØH
1 2 3 ...KP 1
.FLATE 2:
..OBJTYPE AnnenBygning
..NØ
4 5
.SLUTT
        """.strip()
    )

    stats = summarize_tree(document)

    assert stats.has_header is True
    assert stats.has_footer is True
    assert stats.total_objects == 3
    assert stats.object_types == {"PUNKT": 1, "KURVE": 1, "FLATE": 1}
    assert stats.objtypes == {"Bygning": 1, "Takkant": 1, "AnnenBygning": 1}
    assert stats.coordinate_records == 3
    assert stats.coordinate_attribute_counts == {"KP": 1}


def test_parse_text_rejects_duplicate_headers() -> None:
    with pytest.raises(SosiParseError, match="duplicate SOSI header"):
        parse_text(".HODE\n..TEGNSETT UTF-8\n.HODE\n..TEGNSETT UTF-8")


def test_parse_text_rejects_duplicate_footers() -> None:
    with pytest.raises(SosiParseError, match="duplicate SOSI footer"):
        parse_text(".PUNKT 1:\n..OBJTYPE Bygning\n.SLUTT\n.SLUTT")


def test_parse_text_accepts_utf8_bom_prefixed_documents() -> None:
    document = parse_text(
        "\ufeff.HODE\n..TEGNSETT UTF-8\n.PUNKT 1:\n..OBJTYPE Bygning\n"
    )

    assert document.header is not None
    assert document.header.name == "HODE"
    assert [child.name for child in document.children] == ["PUNKT"]


def test_parse_text_appends_wrapped_ref_continuations() -> None:
    document = parse_text(
        """
.FLATE 1:
..REF :27381 :27759 :-27966 :27660 :-28396 :28397 :-28398 :28459 :27540 :27511
:-27466
..NØ
68494776220 5243908477
        """.strip()
    )

    feature = document.children[0]
    assert feature.children[0] == SosiNode(
        name="REF",
        value=":27381 :27759 :-27966 :27660 :-28396 :28397 :-28398 :28459 :27540 :27511 :-27466",
        source_line=2,
    )
