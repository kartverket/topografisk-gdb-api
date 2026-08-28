from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

COMMONS_FILENAME = "commons.yaml"


class DescriptionError(ValueError):
    """Raised when a shared dataset description is invalid for gcjobs."""


@dataclass(frozen=True)
class DatasetDescription:
    name: str
    title: str
    description: str
    import_enabled: bool


def _default_title(name: str) -> str:
    return name.replace("_", " ").title()


def _read_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as file_handle:
        data = yaml.safe_load(file_handle) or {}
    if not isinstance(data, dict):
        raise DescriptionError(f"{path}: expected a mapping at the top level")
    return data


def load_dataset_descriptions(
    descriptions_dir: Path,
    *,
    supported_import_profiles: Iterable[str],
) -> list[DatasetDescription]:
    supported = {profile.casefold() for profile in supported_import_profiles}
    resolved_dir = Path(descriptions_dir)
    if not resolved_dir.exists():
        raise DescriptionError(f"descriptions directory does not exist: {resolved_dir}")
    if not resolved_dir.is_dir():
        raise DescriptionError(f"descriptions path is not a directory: {resolved_dir}")
    datasets: list[DatasetDescription] = []
    seen_names: set[str] = set()

    for path in sorted(resolved_dir.glob("*.yaml")):
        if path.name == COMMONS_FILENAME:
            continue

        raw_dataset = _read_yaml(path)
        raw_name = raw_dataset.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise DescriptionError(f"{path}: dataset must define a non-empty 'name'")

        name = raw_name.strip().casefold()
        if name in seen_names:
            raise DescriptionError(f"{path}: duplicate dataset name '{name}'")
        seen_names.add(name)

        raw_title = raw_dataset.get("title")
        raw_description = raw_dataset.get("description")
        title = (
            raw_title.strip()
            if isinstance(raw_title, str) and raw_title.strip()
            else _default_title(name)
        )
        description = (
            raw_description.strip() if isinstance(raw_description, str) else ""
        )

        datasets.append(
            DatasetDescription(
                name=name,
                title=title,
                description=description,
                import_enabled=name in supported,
            )
        )

    if not datasets:
        raise DescriptionError(f"no dataset descriptions found in {resolved_dir}")

    return datasets
