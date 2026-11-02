# Relationship descriptions

An entry in a collection's `relationships` list declares a link from that collection to another collection in the same dataset.
The collection owning the `relationships` property is called the `source` while the collection referred to is called the `target`.
Relationships are stored on properties of the `source` feature.
The list defaults to empty.

| Key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `property` | string | Nonempty string | Required | Name of the relationship property on the source feature; retains its spelling, including uppercase and non-ASCII characters. |
| `target` | string | [Collection name](./dataset-and-collection-names.md) in the same dataset | Required | Collection referred to by this relationship. |
| `description` | string | Any string | Optional; no default | Human-readable description of the relationship. |

The `target` follows the collection [naming rules](./dataset-and-collection-names.md); `property` does not use those identifier rules.

```yaml
collections:
  - name: building
    geometry: { type: MultiPolygon, srid: 4326 }
    relationships:
      - property: parcels
        target: parcel
  - name: parcel
    geometry: { type: MultiPolygon, srid: 4326 }
```

## Feature representation

In a source feature, a relationship appears under the specified property as an array of objects.
Each object contains `featuretype` with the target collection name and an identifier key: `id` by default, or the leaf of the target collection's `outward_identifier` path.
For example, a `building` feature linked to a `parcel` without an outward identifier looks like this:

```json
{
  "type": "Feature",
  "id": "e50d34e9-65bd-442c-9bb1-9884d9d065fc",
  "geometry": {
    "type": "MultiPolygon",
    "coordinates": [[[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]]
  },
  "properties": {
    "parcels": [
      {"featuretype": "parcel", "id": "153394d7-c0ef-4444-9c7f-d0f38801a17a"}
    ]
  }
}
```

Link writes validate the array, target collection, identifier key, and target feature.
For `feature_model: topology` collections, writes go through `ogc.transaction`, not direct single-feature writes.

If the target collection declares `outward_identifier: identifikasjon.lokalid`, its links use `lokalid` instead of `id`:

```json
{"parcels": [{"featuretype": "parcel", "lokalid": "153394d7-c0ef-4444-9c7f-d0f38801a17a"}]}
```

## Storage

Relationships are stored in separate association tables rather than in a foreign-key column on the source feature.
For each dataset, geocomponents creates an `association_role` table listing which source properties link to which target collections.
It also creates an `association` table holding the actual links: source collection, source feature ID, property, and target feature ID.
To interpret a link under `building`'s `parcels` property, the (`building`, `parcels`) entry in `association_role` identifies `parcel` as the target collection; the link's `target_id` identifies the feature in the `parcel` table.
