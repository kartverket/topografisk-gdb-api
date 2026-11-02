# Server-managed fields

Collections can declare field values supplied by the server rather than stored directly from client input.
The supplied fields are declared using paths where nested objects are separated by dots, as shown in the [example](#example).

| Collection key | Type | Accepted values | Required / default | Meaning |
| --- | --- | --- | --- | --- |
| `outward_identifier` | string | Nested field path (see [example](#example)) | Optional; no default | Projects the feature's UUID into the named object subfield on read. |
| `server_managed` | map | Field paths mapped to tokens listed below | Optional; empty map | Each path names a field; each token selects a server-supplied value from the table below. |

The supported `server_managed` tokens are:

| Token | Behavior |
| --- | --- |
| `timestamp_iso` | Replaces the client value with the current timestamp on write. |
| `outward_identifier` | For a nested object field, projects the feature ID on read; for a top-level scalar field, copies the value at the collection's `outward_identifier` path on write. The scalar form requires `outward_identifier` to be declared. |

[Issue #137](https://github.com/kartverket/topografisk-gdb-api/issues/137) proposes consolidating the two uses of `outward_identifier` into a single identifier declaration.
The final name and location have not yet been decided.

The collection-level `outward_identifier` also supplies an identifier for [upsert](./database-api.md) and can be supplied by a client on create.

## Example

```yaml
fields:
  - name: identifikasjon
    type: object
    fields:
      - name: lokalid
        type: string
      - name: versjonid
        type: string
  - name: oppdateringsdato
    type: timestamp
outward_identifier: identifikasjon.lokalid
server_managed:
  identifikasjon.versjonid: timestamp_iso
  oppdateringsdato: timestamp_iso
```

Here `identifikasjon.versjonid` is a key in the `identifikasjon` object, while `oppdateringsdato` is a top-level scalar field.

For a feature with ID `00000000-0000-0000-0000-00000000000a`, a read response projects the ID into `properties.identifikasjon.lokalid` as well as the top-level GeoJSON `id`.
