"""Description-driven cases for the contract suites.

Shared inputs come from the resolved YAML declarations in descriptions/.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.descriptions.models import ResolvedCollection, ResolvedDataset

DESCRIPTIONS_DIR = Path(__file__).resolve().parents[3] / "descriptions"
DATASETS: list[ResolvedDataset] = load_resolved_datasets(DESCRIPTIONS_DIR)


@dataclass(frozen=True)
class CollectionCase:
    id: str
    dataset: str
    collection: ResolvedCollection


COLLECTION_CASES: list[CollectionCase] = [
    CollectionCase(
        id=(f"{dataset.name.replace('_', '-')}-{collection.name.replace('_', '-')}"),
        dataset=dataset.name,
        collection=collection,
    )
    for dataset in DATASETS
    for collection in dataset.collections
]

SIMPLE_CASES: list[CollectionCase] = [
    case for case in COLLECTION_CASES if case.collection.supports_crud
]
TOPOLOGY_CASES: list[CollectionCase] = [
    case for case in COLLECTION_CASES if not case.collection.supports_crud
]
