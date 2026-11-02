# Shared definitions

An optional `commons.yaml` in the descriptions directory defines fields and types shared across datasets.
If the file is absent, datasets have no shared definitions.

[Issue #139](https://github.com/kartverket/topografisk-gdb-api/issues/139) proposes removing the support for shared definitions.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `base_fields` | list | [Field descriptions](./field-descriptions.md) | Optional; empty list | Attributes added to every collection in every dataset, before its own `fields`. |
| `field_types` | list | [Named types](#named-types) | Optional; empty list | Reusable PostgreSQL types referenced by `type_ref` on a field. |
| `code_lists` | list | [Code lists](#code-lists) | Optional; empty list | Allowed values referenced by `codelist` on a field. |

A collection cannot declare a field with the same name as a `base_fields` entry.
The built-in `id`, `geometry`, `created_at`, and `updated_at` columns are separate from `base_fields`.

## Named types

Each `field_types` entry has a required `name` and `sql_type`, and an optional `description`.
For example, `sql_type: varchar(4)` limits the length of a field that uses that type.

## Code lists

Each `code_lists` entry has a required `name` and a `values` list, which defaults to empty.
Each value has a required `code` and an optional human-readable `label`.
A dataset may also declare codelists in its own [description](./dataset-descriptions.md).
If both the dataset and `commons.yaml` define a codelist with the same name, the dataset's list takes precedence for that dataset.
The database validates field values against the resolved list when writing features.
