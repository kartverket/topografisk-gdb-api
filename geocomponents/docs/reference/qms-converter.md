# QMS converter

`geocomponents.convert` converts a QMS JSON schema into a geocomponents dataset
description in YAML. The converter reads feature types, attribute types, and
code lists from the QMS schema. Geometry settings and collection-specific
identifier settings come from a separate domain YAML document.

## Python API

```python
convert_qms(data: dict, domain: dict, dataset_name: str) -> str
```

`data` is the parsed QMS JSON object, `domain` is the parsed domain YAML
document, and `dataset_name` is the dataset identifier used in the output.
The return value is a YAML string. Both `domain` and its `general` section are
required.

## Command-line interface

The module can be run with `python -m geocomponents.convert`:

```text
python -m geocomponents.convert \
  --uml <qms-json-file> \
  --domain <domain-yaml-file> \
  --output <output-yaml-file> \
  --dataset-name <dataset-identifier>
```

All four options are required. The CLI reads JSON and YAML as UTF-8, writes the
generated YAML as UTF-8, and reports the output path on standard error.

## Domain document

The `general` mapping must define `srid` and `has_z`. It may also define
`outward_identifier` and `server_managed`; these values apply to each
collection unless overridden in that collection's entry under `collections`.
For example:

```yaml
general:
  srid: 5973
  has_z: true
  outward_identifier: identifikasjon.lokalid
  server_managed:
    identifikasjon.versjonid: timestamp_iso
collections:
  spormidt:
    server_managed:
      oppdateringsdato: timestamp_iso
```

Collection keys are normalized collection names. A collection-level
`outward_identifier` or `server_managed` cannot be specified alongside the
same key in `general`; doing so raises `ValueError`.

## Output structure

The output dataset contains `name`, `title`, `description`, `collections`, and
`codelists`.

- `name` is the supplied `dataset_name`.
- `title` is `Objektkatalog.ObjektkatalogFullstendigNavn`, or
  `dataset_name` when that value is empty or absent.
- `description` is the title followed by `Objektkatalog.Versjon` when a version
  is present; otherwise it is the title.
- Each QMS feature type becomes one collection. The collection `title` and
  `description` are copied from the feature type, with an empty description
  when absent. Its geometry includes `type`, `srid`, and `has_z`.
- `outward_identifier` and `server_managed` are included when configured and
  non-empty.
- `fields` contains the converted attributes. `required: true` is included
  when the QMS attribute's `MultiplicityMin` is at least 1.

The YAML preserves Unicode, retains insertion order, and does not emit YAML
aliases.

## Identifier normalization

Collection, field, and codelist names are normalized as follows:

1. Norwegian `ø`, `æ`, and `å` (uppercase or lowercase) are transliterated to
   `o`, `e`, and `a`.
2. The result is lowercased; characters outside `a`–`z`, `0`–`9`, and `_` are
   replaced with `_`.
3. Leading digits and underscores are removed. An empty result becomes `x`.
4. The result is truncated to 40 characters.

Collection titles and descriptions retain their original QMS values.
The dataset name is emitted exactly as supplied.

## Attribute mappings

| QMS attribute type | Output |
| --- | --- |
| `String`, `URI` | `type: string` |
| `Integer` | `type: integer` |
| `DateTime` | `type: timestamp` |
| `Date` | `type: date` |
| `Boolean` | `type: boolean` |
| `Real`, `Number` | `type: number` |
| `Struct` | `type: object` with recursively converted `fields` |
| `CodeList` with a matching default attribute type and non-empty code list | `codelist` reference and a dataset-level code list |
| `CodeList` without a matching non-empty code list | `type: string` |
| Any other type | Omitted |

For code lists, the matching entry in `DefaultAttributeTypes` is found by
attribute UUID. Its `TypeName` supplies the normalized code-list name, and its
`CodeList` values become `values` entries containing `code`. Repeated
references to the same normalized name produce one dataset-level code list;
the first discovered definition is retained.

## Geometry mappings

The first entry in a feature type's `GeometryTypes` is used.

| QMS geometry type | Output geometry type |
| --- | --- |
| `GM_Curve`, `GM_MultiCurve` | `MultiLineString` |
| `GM_Point`, `GM_MultiPoint` | `MultiPoint` |
| `GM_Surface`, `GM_MultiSurface` | `MultiPolygon` |

No fallback is defined for other geometry types; their output geometry `type`
is null. A feature type without a geometry type causes conversion to fail.

## Required input and errors

| Condition | Result |
| --- | --- |
| A feature type has no geometry type | Conversion raises an exception |
| The domain document has no `general` section | Conversion raises an exception |
| `general.srid` is absent or null | Conversion raises an exception |
| `general.has_z` is absent or null | Conversion raises an exception |
| A setting is defined both in `general` and for the collection | Conversion raises `ValueError` |
