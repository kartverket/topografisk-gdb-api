# Field descriptions

Each entry in a collection's `fields` list defines an attribute of its features.
An object field has its own `fields` list for nested attributes.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `name` | string | [Field name](./dataset-and-collection-names.md) | Required | Attribute name. |
| `type` | string | [Builtin types](#builtin-types) | Optional; no default | Selects a builtin type. |
| `type_ref` | string | [Named types](./shared-definitions.md#named-types) | Optional; no default | References a reusable type in `commons.yaml`. |
| `codelist` | string | [Code lists](./shared-definitions.md#code-lists) | Optional; no default | References allowed values validated on writes through the [database API](./database-api.md); the list can be in `commons.yaml` or the dataset description. |
| `required` | boolean | `true` or `false` | Optional; `false` | Requires a value for this attribute. |
| `description` | string | Any string | Optional; no default | Human-readable field description. |
| `fields` | list | Nested field descriptions (see below) | Optional; empty list | Declares nested subfields when `type: object` is used. |
| `indexable` | boolean | `true` or `false` | Optional; `false` | Creates an index on a top-level scalar field or an immediate object subfield. |
| `auto_increment` | boolean | `true` or `false` | Optional; `false` | Uses a PostgreSQL identity column to generate the next integer on insert when no value is supplied; only allowed with `type: integer`. |
| `enum` | list of strings | Any strings | Optional; empty list | Advertises allowed values in the API schema; not enforced by the database. |

Set exactly one of `type`, `type_ref`, or `codelist` on each field.
For `type: object`, provide at least one subfield in `fields`; subfields follow the same typing rules and may themselves be objects.
An object is stored in one JSONB column, and `indexable: true` on an immediate subfield adds an index on that key.

## Builtin types

| Builtin `type` | PostgreSQL type |
| --- | --- |
| `string` | `text` |
| `integer` | `integer` |
| `number` | `double precision` |
| `boolean` | `boolean` |
| `date` | `date` |
| `timestamp` | `timestamptz` |
| `uuid` | `uuid` |
| `object` | `jsonb` |
