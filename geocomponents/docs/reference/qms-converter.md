# QMS converter

`geocomponents.convert` converts a QMS JSON schema into a geocomponents dataset
description in YAML. The converter reads feature types, attribute types, and
code lists from the QMS schema. Geometry settings and collection-specific
identifier settings come from a separate domain YAML document. Note that the
use of the JSON schemas is a temporary measure, the format of the UML input file
will be changed later. The important takeaway from this reference is the
structure of the domain file.

## Python API

```python
convert_qms(data: dict, domain: dict, dataset_name: str) -> str
```

`data` is the parsed QMS JSON object, `domain` is the parsed domain YAML
document, and `dataset_name` is the dataset identifier used in the output.
The return value is a YAML string.

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
generated YAML as UTF-8, and returns the output path of the generated file.

## Domain document

The `general` mapping must define `srid` and `has_z`. `outward_identifier`
and `server_managed` can be defined for either the entire dataset under
`general` or for each specific collection. The following is an example of
a domain file:

```yaml
general:
  srid: 5973
  has_z: true
  server_managed:
    identifikasjon.versjonid: timestamp_iso
collections:
  spormidt:
    outward_identifier: identifikasjon.lokalid
```

Collection keys are normalized collection names. A collection-level
`outward_identifier` or `server_managed` cannot be specified alongside the
same key in `general`; doing so raises `ValueError`.

## Output structure

The structure of the generated YAML file is documented in [Dataset descriptions](./dataset-descriptions.md).

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
