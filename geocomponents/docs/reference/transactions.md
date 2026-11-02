# Transactions

> **Work in progress:** Transactions are not ready for use.
> The interface and document structure may change; this reference is provisional and should not be used as implementation guidance.
> Revised documentation will follow once the structure is more firmly settled.

The database exposes a function `ogc.transaction(dataset text, document jsonb)` that allows writing multiple features at simultaneously.

The function takes the name of the dataset and a jsonb document describing the transaction and returns a jsonb report describing the results of the transaction.

## Document

The document contains following fields:

| Field | Meaning |
| --- | --- |
| `semantic` | Transaction mode. "atomic" for "all or nothing" transactions. |
| `transaction` | Ordered list of actions on features. If absent or `null`, it is treated as an empty list; other non-list values are rejected. |
| `transaction[].collection` | Collection to write to. |
| `transaction[].action` | `insert` creates a feature; `update` changes fields present in a feature; `replace` replaces a feature's content; `delete` removes a feature. |
| `transaction[].feature` | GeoJSON feature to write for `insert`, `update`, or `replace`; not used for `delete`. |
| `transaction[].id` | ID of the existing feature for `update`, `replace`, or `delete`. For `insert`, supply the UUID as `feature.id` to choose the new feature's ID. |

Later items in the same document can refer to that feature by its ID or `outward_identifier`.
Items must be ordered so that a referenced target exists when its link is written.
See example document below:

```jsonc
// Example document
{
  "semantic": "atomic",
  "transaction": [
    {
      "action": "insert",
      "collection": "border",
      "feature": {
        "type": "Feature",
        "id": "153394d7-c0ef-4444-9c7f-d0f38801a17a",
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]},
        "properties": {"identifikasjon": {"lokalid": "153394d7-c0ef-4444-9c7f-d0f38801a17a"}}
      }
    },
    {
      "action": "insert",
      "collection": "surface",
      "feature": {
        "type": "Feature",
        "id": "e50d34e9-65bd-442c-9bb1-9884d9d065fc",
        "geometry": null,
        "properties": {
          "borderedBy": [
            {"featuretype": "border", "identifikasjon.lokalid": "153394d7-c0ef-4444-9c7f-d0f38801a17a"}
          ]
        }
      }
    }
  ]
}
```

## Report

The function returns a report describing whether the writes were accepted or rolled back.
An unknown dataset or a missing generated database object raises a database error instead of returning a report.

Every returned report has these keys:

| Key | Meaning |
| --- | --- |
| `committed` | `true` when the function accepted all writes; `false` when it rolled them back. A caller can still roll back its own SQL transaction. |
| `phase` | The stage that completed or failed: `document`, `items`, `structure`, or `geometry`. |
| `reason`, `sqlstate` | Top-level error message and PostgreSQL error code for a document failure; `null` otherwise. |
| `items` | One result per applied item on success, the rejected item on an item failure, or an empty array for document and validation failures. |
| `structure`, `geometry` | Findings from structural and geometry validation; always present as arrays, empty when there are no findings. |

For the two inserts above, a successful report names both created IDs:

```json
{
  "committed": true,
  "phase": "items",
  "reason": null,
  "sqlstate": null,
  "items": [
    {"index": 0, "action": "insert", "collection": "border1", "id": "153394d7-c0ef-4444-9c7f-d0f38801a17a", "status": "created", "sqlstate": null, "reason": null},
    {"index": 1, "action": "insert", "collection": "surface2", "id": "e50d34e9-65bd-442c-9bb1-9884d9d065fc", "status": "created", "sqlstate": null, "reason": null}
  ],
  "structure": [],
  "geometry": []
}
```

Each item has a zero-based `index`, `action`, `collection`, `id`, `status`, `sqlstate`, and `reason`.
The success status is `created` for insert, `updated` for update and replace, and `deleted` for delete.

| Phase | Meaning |
| --- | --- |
| `document` | The document was rejected before applying items; `reason` and `sqlstate` are set at the top level. |
| `items` | An item failed; `items` contains only the rejected item, with `status: rejected`, its error `reason`, and its `sqlstate`. |
| `structure` | Structural checks failed after applying items; `structure` contains the findings. |
| `geometry` | Structural checks passed but geometry checks failed; `geometry` contains the findings. |

On an item failure or a findings report, top-level `reason` and `sqlstate` are `null`.
Only the rejected item appears in `items` after an item failure; earlier results are discarded because the writes were rolled back.
For example, if the linked boundary in the document above does not exist when the surface is inserted, that surface item is rejected and the previously inserted items are rolled back.
An invalid combination of boundary roles instead produces a structural finding:

```json
{
  "committed": false,
  "phase": "structure",
  "reason": null,
  "sqlstate": null,
  "items": [],
  "structure": [
    {
      "id": "870a1fad-3b9f-4de5-b2af-2b2cb19eb372",
      "rule": "footprint",
      "valid": false,
      "reason": "conflicting_boundary_roles",
      "details": {"roles": ["boundedByConditional", "boundedByOuter"]},
      "members": 2,
      "included": 2,
      "collection": "surface"
    }
  ],
  "geometry": []
}
```

Here `structure` contains the failing check; `items` is empty because the whole atomic document was rolled back.
If the boundary lines do not form a valid surface, `phase` is `geometry` and the findings appear in `geometry` instead.
