# QMS converter

`geocomponents.convert` converts a QMS JSON schema into a geocomponents dataset
description in YAML. The converter reads feature types, attribute types, and
code lists from the QMS schema. Geometry settings and collection-specific
identifier settings come from a separate domain YAML document. Note that the
use of the JSON schemas is a temporary measure, the format of the UML input file
will be changed later. The important takeaway from this reference is the
structure of the domain file.

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

The domain document is documented in [Domain document](./domain-document.md).

## Output structure

The structure of the generated YAML file is documented in [Dataset descriptions](./dataset-descriptions.md).

## Identifier normalization

Collection, field, and codelist names are normalized to follow [dataset and collection names](./dataset-and-collection-names.md)

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
