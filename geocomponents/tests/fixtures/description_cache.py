"""Shared parsed description cache for the test harness."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from geocomponents.descriptions.loader import load_resolved_datasets
from geocomponents.descriptions.models import ResolvedDataset

DESCRIPTIONS_DIR = Path(__file__).resolve().parents[3] / "descriptions"


@cache
def resolved_datasets() -> tuple[ResolvedDataset, ...]:
    return tuple(load_resolved_datasets(DESCRIPTIONS_DIR))


def resolved_dataset(name: str) -> ResolvedDataset:
    return next(dataset for dataset in resolved_datasets() if dataset.name == name)
