"""Named rejection cases for ogc.transaction contract tests."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fixtures.collection_cases import COLLECTION_CASES
from fixtures.features import _sample_feature

PARCELS = next(
    case.collection
    for case in COLLECTION_CASES
    if case.dataset == "cadastre" and case.collection.name == "parcels"
)


@dataclass(frozen=True)
class RejectedItem:
    index: int
    action: str | None
    collection: str | None
    id_is_null: bool
    sqlstate: str


@dataclass(frozen=True)
class RejectionCase:
    id: str
    preceding_ok_items: int
    failing_item: dict
    expected: RejectedItem


@dataclass(frozen=True)
class MalformedDocumentCase:
    id: str
    document: dict


REJECTION_CASES = [
    RejectionCase(
        "missing-action-key-after-success",
        1,
        {"collection": "parcels"},
        RejectedItem(1, None, "parcels", True, "P0001"),
    ),
    RejectionCase(
        "null-action-after-success",
        1,
        {"action": None, "collection": "parcels"},
        RejectedItem(1, None, "parcels", True, "P0001"),
    ),
    RejectionCase(
        "unknown-verb-after-success",
        1,
        {"action": "bogus", "collection": "parcels"},
        RejectedItem(1, "bogus", "parcels", True, "P0001"),
    ),
    RejectionCase(
        "unknown-collection-after-success",
        1,
        {
            "action": "insert",
            "collection": "bogus-collection",
            "feature": _sample_feature(
                PARCELS,
                fid=uuid4(),
                properties={"label": "unknown-collection", "area_m2": 150.0},
            ),
        },
        RejectedItem(1, "insert", "bogus-collection", False, "P0001"),
    ),
    RejectionCase(
        "malformed-geometry-string",
        1,
        {
            "action": "insert",
            "collection": "parcels",
            "feature": _sample_feature(
                PARCELS,
                geometry="nonsense",
                properties={"label": "bad-geometry-string", "area_m2": 160.0},
            ),
        },
        RejectedItem(1, "insert", "parcels", True, "P0001"),
    ),
    RejectionCase(
        "postgis-rejects-geojson-object",
        1,
        {
            "action": "insert",
            "collection": "parcels",
            "feature": _sample_feature(
                PARCELS,
                geometry={"type": PARCELS.geometry_type, "coordinates": "nonsense"},
                properties={"label": "bad-geometry", "area_m2": 170.0},
            ),
        },
        RejectedItem(1, "insert", "parcels", True, "XX000"),
    ),
    RejectionCase(
        "delete-of-nonexistent-id",
        1,
        {
            "action": "delete",
            "collection": "parcels",
            "id": str(uuid4()),
        },
        RejectedItem(1, "delete", "parcels", False, "P0001"),
    ),
]

MALFORMED_DOCUMENT_CASES = [
    MalformedDocumentCase(
        "missing-semantic",
        {"transaction": []},
    ),
    MalformedDocumentCase(
        "wrong-semantic",
        {"semantic": "batch", "transaction": []},
    ),
    MalformedDocumentCase(
        "transaction-not-an-array",
        {"semantic": "atomic", "transaction": {}},
    ),
]
