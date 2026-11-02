# Geometry descriptions

Each collection has one primary geometry, declared by its `geometry` object.
If `geometry` is omitted, the collection uses a required 2D `Point` with SRID 4326.
Geometry is separate from the collection's attribute `fields`.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `type` | string | Geometry types listed below | Optional; `Point` | PostGIS geometry type; the declared type is enforced, so `MultiPolygon` does not accept `Polygon`. |
| `srid` | integer | Spatial reference identifier | Optional; `4326` | 4326 uses WGS84 longitude/latitude coordinates. |
| `has_z` | boolean | `true` or `false` | Optional; `false` | Stores coordinates with a Z dimension using the corresponding PostGIS `*Z` type. |
| `required` | boolean | `true` or `false` | Optional; `true` | Requires a geometry on direct feature writes when no derived geometry is configured. |
| `derived` | object | [Derived geometry rules](#derived-geometries) | Optional; no default | Constructs geometry from related features. |

Allowed `type` values are `Point`, `MultiPoint`, `LineString`, `MultiLineString`, `Polygon`, `MultiPolygon`, and `GeometryCollection`.

## Multiple geometries

The current description format declares one primary geometry per collection.
It does not support additional geometry attributes on a feature.

## Derived geometries

The optional `derived` object selects a rule for constructing the collection's geometry from related features.

### Footprint

`footprint` builds a `MultiPolygon` surface from linked boundary features.
The collection must declare relationships for each boundary role; their targets must have `LineString` or `MultiLineString` geometry and the same SRID as the surface.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `rule` | string | `footprint` | Required | Derives a surface from linked linework. |
| `areas` | string | `one` or `many` | Required | Whether multiple disjoint areas are accepted. |
| `holes` | string | `allowed` or `forbidden` | Required | Whether holes in the derived surface are accepted. |
| `one_of` | list of lists | Nonempty alternatives of boundary roles (see below) | Required | Alternative sets of boundary roles; at least one alternative is required. |

Each role in `one_of` is either a relationship property name or an object with `name` and optional `when`.
`when` names a boolean field on the target collection; that role participates only when the field is true.

```yaml
geometry:
  type: MultiPolygon
  srid: 4326
  required: false
  derived:
    rule: footprint
    areas: many
    holes: forbidden
    one_of:
      - [boundedByOuter]
      - [{name: boundedByConditional, when: is_bounding}]
```

`feature_model: topology` and `derived` are separate settings: a topology collection may declare direct geometry, derived geometry, or both.
