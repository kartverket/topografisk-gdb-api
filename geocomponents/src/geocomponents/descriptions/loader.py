"""Load + validate + resolve dataset descriptions.

Pipeline: read YAML -> validate raw structure (Pydantic) -> merge the commons
base schema into every collection, resolve type/codelist/relationship refs ->
return DB-neutral ``ResolvedDataset`` objects.

This is the layer a future GML/UML -> description factory would target: it just
needs to emit YAML that parses into the raw models here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from geocomponents.descriptions.models import (
    BUILTIN_SQL_TYPES,
    CodeList,
    CollectionDef,
    Commons,
    DatasetDef,
    FieldDef,
    FieldType,
    ResolvedCollection,
    ResolvedDataset,
    ResolvedDerivedDef,
    ResolvedDerivedRole,
    ResolvedField,
    ResolvedRelationship,
)
from geocomponents.processes.registry import known_process_ids


class DescriptionError(ValueError):
    """Raised when a description document is structurally invalid."""


_RESERVED_COLLECTION_NAMES = frozenset({"association", "association_role"})
_LINE_GEOMETRY_TYPES = frozenset({"LineString", "MultiLineString"})


@dataclass(frozen=True)
class PreparedCollection:
    collection: CollectionDef
    where: str
    fields: tuple[ResolvedField, ...]
    upsert_field: str | None
    upsert_path: str | None


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
    except Exception as exc:
        raise DescriptionError(f"invalid commons file {path}: {exc}") from exc


def load_dataset(path: Path) -> DatasetDef:
    try:
        return DatasetDef.model_validate(_read_yaml(path))
    except Exception as exc:
        raise DescriptionError(f"invalid dataset file {path}: {exc}") from exc


def _validate_collection_name(name: str, *, where: str) -> None:
    if name in _RESERVED_COLLECTION_NAMES:
        raise DescriptionError(
            f"{where}: collection name '{name}' is reserved for generated tables"
        )


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
    """Resolve one FieldDef into a DB-neutral ResolvedField."""
    if fld.type == "object":
        # Recurse into sub-fields; compose the where path so error messages
        # name the full field path (e.g. "… / field 'kvalitet' / field 'x'").
        child_where = f"{where} / field '{fld.name}'"
        sub = tuple(
            _resolve_field(sf, types, codelists, where=child_where) for sf in fld.fields
        )
        return ResolvedField(
            fld.name,
            "jsonb",
            fld.required,
            sub_fields=sub,
            enum=tuple(fld.enum),
            indexable=fld.indexable,
        )

    if fld.codelist is not None:
        if fld.codelist not in codelists:
            raise DescriptionError(
                f"{where}: field '{fld.name}' references unknown code list "
                f"'{fld.codelist}'"
            )
        # Code-list columns are plain text; code values are stored so the
        # function generator can emit DB-level validation.
        cl = codelists[fld.codelist]
        return ResolvedField(
            fld.name,
            "text",
            fld.required,
            codelist=fld.codelist,
            auto_increment=fld.auto_increment,
            enum=tuple(fld.enum),
            indexable=fld.indexable,
            codelist_values=tuple(v.code for v in cl.values),
        )

    if fld.type_ref is not None:
        if fld.type_ref not in types:
            raise DescriptionError(
                f"{where}: field '{fld.name}' references unknown type '{fld.type_ref}'"
            )
        return ResolvedField(
            fld.name,
            types[fld.type_ref].sql_type,
            fld.required,
            auto_increment=fld.auto_increment,
            enum=tuple(fld.enum),
            indexable=fld.indexable,
        )

    if fld.type is not None:
        if fld.type not in BUILTIN_SQL_TYPES:
            raise DescriptionError(
                f"{where}: field '{fld.name}' has unknown builtin type "
                f"'{fld.type}' (known: {', '.join(sorted(BUILTIN_SQL_TYPES))})"
            )
        return ResolvedField(
            fld.name,
            BUILTIN_SQL_TYPES[fld.type],
            fld.required,
            auto_increment=fld.auto_increment,
            enum=tuple(fld.enum),
            indexable=fld.indexable,
        )

    # FieldDef enforces "exactly one of type / type_ref / codelist" at parse time,
    # so this branch is unreachable.
    raise AssertionError(
        f"{where}: field '{fld.name}' has no type source (should be unreachable)"
    )


def _resolve_dot_path(
    fields: tuple[ResolvedField, ...],
    dot_path: str,
    *,
    where: str,
    kind: str,
) -> ResolvedField:
    """Walk a dot-path through a resolved field tree; raise DescriptionError if any segment is missing."""
    parts = dot_path.split(".")
    current = fields
    found: ResolvedField | None = None
    for part in parts:
        found = next((f for f in current if f.name == part), None)
        if found is None:
            raise DescriptionError(
                f"{where}: {kind} path '{dot_path}' — segment '{part}' not found"
            )
        current = found.sub_fields
    if found is None:
        # Guards against callers passing an empty dot_path.
        raise DescriptionError(f"{where}: {kind} path cannot be empty")
    return found


def _upsert_alias_paths(
    fields: tuple[ResolvedField, ...],
    *,
    outward_identifier_path: str | None,
) -> dict[str, str]:
    alias_paths: dict[str, str] = {field.name: field.name for field in fields}
    for field in fields:
        for sub_field in field.sub_fields:
            alias_paths.setdefault(
                f"{field.name}_{sub_field.name}", f"{field.name}.{sub_field.name}"
            )
    if outward_identifier_path:
        alias_paths.setdefault(outward_identifier_path, outward_identifier_path)
        alias_paths.setdefault(
            outward_identifier_path.rsplit(".", 1)[-1], outward_identifier_path
        )
    return alias_paths


def _resolved_upsert_field(
    coll: CollectionDef,
    resolved_fields: tuple[ResolvedField, ...],
) -> str | None:
    if coll.outward_identifier:
        return coll.outward_identifier

    if any(field.name == "lokalid" for field in resolved_fields):
        return "lokalid"

    return None


def _resolve_relationships(
    coll: CollectionDef,
    collection_names: set[str],
    *,
    where: str,
) -> tuple[ResolvedRelationship, ...]:
    resolved_rels: list[ResolvedRelationship] = []
    for rel in coll.relationships:
        if rel.target not in collection_names:
            raise DescriptionError(
                f"{where}: relationship '{rel.property}' targets unknown "
                f"collection '{rel.target}' (cross-dataset refs not allowed)"
            )
        resolved_rels.append(ResolvedRelationship(rel.property, rel.target))
    return tuple(resolved_rels)


def _resolve_derived(
    coll: CollectionDef,
    relationships: tuple[ResolvedRelationship, ...],
    collections_by_name: dict[str, CollectionDef],
    resolved_fields_by_collection: dict[str, tuple[ResolvedField, ...]],
    *,
    where: str,
) -> ResolvedDerivedDef | None:
    derived = coll.geometry.derived
    if derived is None:
        return None

    relationships_by_property = {rel.property: rel for rel in relationships}
    resolved_alternatives: list[tuple[ResolvedDerivedRole, ...]] = []
    for alternative in derived.one_of:
        resolved_roles: list[ResolvedDerivedRole] = []
        for role in alternative:
            relationship = relationships_by_property.get(role.name)
            if relationship is None:
                raise DescriptionError(
                    f"{where}: derived property '{role.name}' is not a declared "
                    "relationship"
                )

            target_collection = collections_by_name[relationship.target]
            if target_collection.geometry.type not in _LINE_GEOMETRY_TYPES:
                raise DescriptionError(
                    f"{where}: derived property '{role.name}' targets collection "
                    f"'{relationship.target}' with geometry type "
                    f"'{target_collection.geometry.type}' (expected LineString or "
                    "MultiLineString)"
                )
            if target_collection.geometry.srid != coll.geometry.srid:
                raise DescriptionError(
                    f"{where}: derived property '{role.name}' targets collection "
                    f"'{relationship.target}' with SRID {target_collection.geometry.srid} "
                    f"but the surface geometry uses SRID {coll.geometry.srid}"
                )

            when_field = None
            if role.when is not None:
                target_fields = resolved_fields_by_collection[relationship.target]
                target_field = next(
                    (field for field in target_fields if field.name == role.when),
                    None,
                )
                if target_field is None:
                    raise DescriptionError(
                        f"{where}: derived property '{role.name}' names unknown "
                        f"when field '{role.when}' on target collection "
                        f"'{relationship.target}'"
                    )
                if target_field.sql_type != "boolean":
                    raise DescriptionError(
                        f"{where}: derived property '{role.name}' names non-boolean "
                        f"when field '{role.when}' on target collection "
                        f"'{relationship.target}'"
                    )
                when_field = target_field.name

            resolved_roles.append(
                ResolvedDerivedRole(
                    property=role.name,
                    target=relationship.target,
                    when_field=when_field,
                )
            )
        resolved_alternatives.append(tuple(resolved_roles))

    return ResolvedDerivedDef(
        rule=derived.rule,
        areas=derived.areas,
        holes=derived.holes,
        one_of=tuple(resolved_alternatives),
    )


def _validate_bounds(
    coll: CollectionDef,
    targeted_collections: set[str],
    *,
    where: str,
) -> None:
    if coll.bounds is None:
        return
    if coll.name not in targeted_collections:
        raise DescriptionError(
            f"{where}: bounds declared on untargeted collection '{coll.name}'"
        )
    if coll.geometry.type not in _LINE_GEOMETRY_TYPES:
        raise DescriptionError(
            f"{where}: bounds requires geometry type LineString or "
            f"MultiLineString (got '{coll.geometry.type}')"
        )


def resolve_dataset(dataset: DatasetDef, commons: Commons) -> ResolvedDataset:
    types = {t.name: t for t in commons.field_types}
    # Dataset-local codelists take precedence over commons codelists.
    codelists: dict[str, CodeList] = {c.name: c for c in commons.code_lists}
    codelists.update({c.name: c for c in dataset.codelists})
    targeted_collections = {
        rel.target for coll in dataset.collections for rel in coll.relationships
    }
    collection_names = {c.name for c in dataset.collections}
    collections_by_name = {c.name: c for c in dataset.collections}

    unknown_processes = set(dataset.processes) - known_process_ids()
    if unknown_processes:
        raise DescriptionError(
            f"dataset '{dataset.name}': unknown process(es) "
            f"{sorted(unknown_processes)} (known: {sorted(known_process_ids())})"
        )

    prepared_collections: list[PreparedCollection] = []
    resolved_fields_by_collection: dict[str, tuple[ResolvedField, ...]] = {}
    resolved_collections: list[ResolvedCollection] = []
    for coll in dataset.collections:
        where = f"dataset '{dataset.name}' / collection '{coll.name}'"
        _validate_collection_name(coll.name, where=where)

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

        resolved_tuple = tuple(resolved_fields)
        if coll.outward_identifier:
            _resolve_dot_path(
                resolved_tuple,
                coll.outward_identifier,
                where=where,
                kind="outward_identifier",
            )
        for path in coll.server_managed:
            _resolve_dot_path(
                resolved_tuple,
                path,
                where=where,
                kind="server_managed",
            )

        resolved_upsert_field = _resolved_upsert_field(coll, resolved_tuple)
        upsert_alias_paths = _upsert_alias_paths(
            resolved_tuple,
            outward_identifier_path=coll.outward_identifier,
        )
        if (
            resolved_upsert_field is not None
            and resolved_upsert_field not in upsert_alias_paths
        ):
            raise DescriptionError(
                f"{where}: resolved upsert field references unknown field "
                f"'{resolved_upsert_field}'"
            )
        auto_increment_fields = {
            fld.name for fld in merged_fields if fld.auto_increment
        }
        if (
            resolved_upsert_field is not None
            and upsert_alias_paths[resolved_upsert_field] in auto_increment_fields
        ):
            raise DescriptionError(
                f"{where}: resolved upsert field cannot use auto-increment field "
                f"'{resolved_upsert_field}'"
            )

        upsert_path = (
            upsert_alias_paths[resolved_upsert_field]
            if resolved_upsert_field is not None
            else None
        )

        resolved_fields_by_collection[coll.name] = resolved_tuple
        prepared_collections.append(
            PreparedCollection(
                collection=coll,
                where=where,
                fields=resolved_tuple,
                upsert_field=resolved_upsert_field,
                upsert_path=upsert_path,
            )
        )

    for prepared in prepared_collections:
        _validate_bounds(
            prepared.collection,
            targeted_collections,
            where=prepared.where,
        )
        resolved_rels = _resolve_relationships(
            prepared.collection,
            collection_names,
            where=prepared.where,
        )
        resolved_derived = _resolve_derived(
            prepared.collection,
            resolved_rels,
            collections_by_name,
            resolved_fields_by_collection,
            where=prepared.where,
        )
        resolved_collections.append(
            ResolvedCollection(
                name=prepared.collection.name,
                title=prepared.collection.title
                or prepared.collection.name.replace("_", " ").title(),
                description=prepared.collection.description or "",
                feature_model=prepared.collection.feature_model,
                bounds=prepared.collection.bounds,
                geometry_type=prepared.collection.geometry.type,
                srid=prepared.collection.geometry.srid,
                has_z=prepared.collection.geometry.has_z,
                geometry_required=prepared.collection.geometry.required,
                fields=prepared.fields,
                relationships=resolved_rels,
                derived=resolved_derived,
                upsert_field=prepared.upsert_field,
                upsert_path=prepared.upsert_path,
                outward_identifier_path=prepared.collection.outward_identifier,
                server_managed_paths=dict(prepared.collection.server_managed),
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
    """Read every ``*.yaml`` in ``descriptions_dir``, validate, and return the
    resolved datasets with the optional ``commons.yaml`` merged into them,
    sorted by name.
    """

    descriptions_dir = Path(descriptions_dir)
    commons_path = descriptions_dir / commons_filename
    commons = load_commons(commons_path) if commons_path.exists() else Commons()

    datasets: list[ResolvedDataset] = []
    for path in sorted(descriptions_dir.glob("*.yaml")):
        if path.name == commons_filename:
            continue
        datasets.append(resolve_dataset(load_dataset(path), commons))
    return datasets
