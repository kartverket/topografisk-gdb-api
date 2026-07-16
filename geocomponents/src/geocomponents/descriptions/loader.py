"""Load + validate + resolve dataset descriptions.

Pipeline: read YAML -> validate raw structure (Pydantic) -> merge the commons
base schema into every collection, resolve type/codelist/relationship refs ->
return DB-neutral ``ResolvedDataset`` objects.

This is the layer a future GML/UML -> description factory would target: it just
needs to emit YAML that parses into the raw models here.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ..processes.registry import known_process_ids
from .models import (
    BUILTIN_SQL_TYPES,
    CodeList,
    Commons,
    DatasetDef,
    FieldDef,
    FieldType,
    ResolvedCollection,
    ResolvedDataset,
    ResolvedField,
    ResolvedRelationship,
)


class DescriptionError(ValueError):
    """Raised when a description document is structurally invalid."""


def _read_yaml(path: Path) -> dict:
    # Pin UTF-8; host locale defaults would mojibake Norwegian å/ø/æ.
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise DescriptionError(f"{path}: expected a mapping at the top level")
    return data


def load_commons(path: Path) -> Commons:
    try:
        return Commons.model_validate(_read_yaml(path))
    except Exception as exc:  # noqa: BLE001 - surface a clear message
        raise DescriptionError(f"invalid commons file {path}: {exc}") from exc


def load_dataset(path: Path) -> DatasetDef:
    try:
        return DatasetDef.model_validate(_read_yaml(path))
    except Exception as exc:  # noqa: BLE001
        raise DescriptionError(f"invalid dataset file {path}: {exc}") from exc


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------
def _resolve_field(
    fld: FieldDef,
    types: dict[str, FieldType],
    codelists: dict[str, CodeList],
    *,
    where: str,
) -> ResolvedField:
    if fld.codelist is not None:
        if fld.codelist not in codelists:
            raise DescriptionError(
                f"{where}: field '{fld.name}' references unknown code list "
                f"'{fld.codelist}'"
            )
        # Code-list columns are plain text for now; DB-side enforcement is a
        # deferred 'validation in the DB' concern.
        return ResolvedField(fld.name, "text", fld.required, codelist=fld.codelist)

    if fld.type_ref is not None:
        if fld.type_ref not in types:
            raise DescriptionError(
                f"{where}: field '{fld.name}' references unknown type '{fld.type_ref}'"
            )
        return ResolvedField(fld.name, types[fld.type_ref].sql_type, fld.required)

    if fld.type is not None:
        if fld.type not in BUILTIN_SQL_TYPES:
            raise DescriptionError(
                f"{where}: field '{fld.name}' has unknown builtin type "
                f"'{fld.type}' (known: {', '.join(sorted(BUILTIN_SQL_TYPES))})"
            )
        return ResolvedField(fld.name, BUILTIN_SQL_TYPES[fld.type], fld.required)

    raise DescriptionError(
        f"{where}: field '{fld.name}' must set one of type / type_ref / codelist"
    )


def resolve_dataset(dataset: DatasetDef, commons: Commons) -> ResolvedDataset:
    types = {t.name: t for t in commons.field_types}
    codelists = {c.name: c for c in commons.code_lists}
    collection_names = {c.name for c in dataset.collections}

    unknown_processes = set(dataset.processes) - known_process_ids()
    if unknown_processes:
        raise DescriptionError(
            f"dataset '{dataset.name}': unknown process(es) "
            f"{sorted(unknown_processes)} (known: {sorted(known_process_ids())})"
        )

    resolved_collections: list[ResolvedCollection] = []
    for coll in dataset.collections:
        where = f"dataset '{dataset.name}' / collection '{coll.name}'"

        # Shared base schema: commons.base_fields are prepended, then the
        # collection's own fields. (id/geometry/audit columns are added later
        # by the schema builder, not modelled as ordinary fields.)
        merged_fields: list[FieldDef] = [*commons.base_fields, *coll.fields]
        seen: set[str] = set()
        resolved_fields: list[ResolvedField] = []
        for fld in merged_fields:
            if fld.name in seen:
                raise DescriptionError(f"{where}: duplicate field name '{fld.name}'")
            seen.add(fld.name)
            resolved_fields.append(_resolve_field(fld, types, codelists, where=where))

        resolved_rels: list[ResolvedRelationship] = []
        for rel in coll.relationships:
            if rel.target not in collection_names:
                raise DescriptionError(
                    f"{where}: relationship '{rel.name}' targets unknown "
                    f"collection '{rel.target}' (cross-dataset refs not allowed)"
                )
            resolved_rels.append(ResolvedRelationship(rel.name, rel.target))

        resolved_collections.append(
            ResolvedCollection(
                name=coll.name,
                title=coll.title or coll.name.replace("_", " ").title(),
                description=coll.description or "",
                feature_model=coll.feature_model,
                geometry_type=coll.geometry.type,
                srid=coll.geometry.srid,
                fields=tuple(resolved_fields),
                relationships=tuple(resolved_rels),
            )
        )

    return ResolvedDataset(
        name=dataset.name,
        title=dataset.title or dataset.name.replace("_", " ").title(),
        description=dataset.description or "",
        processes=tuple(dataset.processes),
        collections=tuple(resolved_collections),
    )


def load_resolved_datasets(
    descriptions_dir: Path,
    commons_filename: str = "commons.yaml",
) -> list[ResolvedDataset]:
    """Load the commons + every ``*.yaml`` dataset file in a directory."""

    descriptions_dir = Path(descriptions_dir)
    commons_path = descriptions_dir / commons_filename
    commons = load_commons(commons_path) if commons_path.exists() else Commons()

    datasets: list[ResolvedDataset] = []
    for path in sorted(descriptions_dir.glob("*.yaml")):
        if path.name == commons_filename:
            continue
        datasets.append(resolve_dataset(load_dataset(path), commons))
    return datasets
