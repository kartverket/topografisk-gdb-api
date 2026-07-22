---
name: ogc-api-features
description: 'OGC API - Features write-operations reference (Parts 4 and 11). Use when: implementing, reviewing, or debugging any Create / Replace / Update / Delete on features exposed via /collections/{collectionId}/items; adding Atomic or Batch Transactions; declaring conformance classes; choosing HTTP status codes, headers (ETag, Location, Prefer, If-Match), media types (application/geo+json, application/json, application/merge-patch+json), or error formats (application/problem+json); validating that responses satisfy OGC requirement IDs. Trigger keywords: OGC, OGC API Features, conformance, collections endpoint, features endpoint, feature CRUD, batch transactions, atomic transactions, GeoJSON write.'
argument-hint: '[implement|review|conformance] <topic>'
---

# OGC API - Features (Parts 4 & 11)

Reference and workflow for implementing and validating OGC API - Features compliant
write operations. Backend- and framework-agnostic; applies wherever a service claims
conformance to Part 4 or Part 11.

## Scope

This skill covers:

- **Part 4 — Create, Replace, Update and Delete** (`POST` / `PUT` / `PATCH` / `DELETE`
  on items). Canonical URL: <https://docs.ogc.org/DRAFTS/20-002r1.html>
- **Part 11 — Atomic and Batch Transactions** (multi-feature transactional writes).
  Canonical URL: <https://docs.ogc.org/DRAFTS/23-057r1.html>

Depends on (assumed already conformant, out of scope for this skill):

- Part 1 — Core: <http://docs.ogc.org/is/17-069r4/17-069r4.html>
- Part 2 — CRS by Reference: <http://docs.ogc.org/is/18-058r1/18-058.html>

If offline HTML copies of the specs are present under an `ogc-standards/` folder in
the consuming workspace, prefer them for exact requirement wording; otherwise use the
canonical URLs above.

## When to Use

Load this skill when the user is:

1. Adding or changing any endpoint that creates, replaces, updates, or deletes
   features (typically `POST` / `PUT` / `PATCH` / `DELETE` on
   `/collections/{collectionId}/items` or `/{featureId}`).
2. Reviewing whether an existing write endpoint is spec-compliant.
3. Declaring or updating conformance URIs advertised by a `/conformance` endpoint.
4. Deciding response status codes, required headers (`Location`, `ETag`,
   `Last-Modified`, `Prefer` / `Preference-Applied`), or media types.
5. Designing a batch or atomic transaction endpoint (Part 11).
6. Writing contract tests against the Abstract Test Suites in the specs.

Do **not** load this skill for:

- Read-only feature queries (Part 1 — out of scope).
- Pure database/DDL work with no HTTP surface.
- Domain-model questions unrelated to the HTTP API.

## Procedure

Follow these steps for any change touching write endpoints on features.

### 1. Identify the requirements class

Determine which conformance class(es) the change belongs to. See
[references/conformance-classes.md](./references/conformance-classes.md).

Common classes:

- Part 4: *Create/Replace/Delete Features*, *Update Features*, *Features*, *Features
  (GeoJSON)*.
- Part 11: *Atomic Transactions*, *Batch Transactions*.

Each declared conformance URI **must** be listed in the `/conformance` response.

### 2. Match HTTP method to operation

| Operation | Method | Path | Body |
|-----------|--------|------|------|
| Create one feature | `POST` | `/collections/{cid}/items` | GeoJSON Feature |
| Create many features | `POST` | `/collections/{cid}/items` | GeoJSON FeatureCollection |
| Full replace | `PUT` | `/collections/{cid}/items/{fid}` | GeoJSON Feature |
| Partial update | `PATCH` | `/collections/{cid}/items/{fid}` | JSON Merge Patch or similar |
| Delete | `DELETE` | `/collections/{cid}/items/{fid}` | none |

Details, expected status codes and edge cases: see
[references/part-4-crud.md](./references/part-4-crud.md).

### 3. Validate headers and status codes

Check the request/response header requirements for the chosen operation. See
[references/http-semantics.md](./references/http-semantics.md) for the mapping
of status codes (`201`, `204`, `303`, `412`, `415`, `422`, …) and required headers
(`Location`, `ETag`, `Content-Type`, `Prefer`/`Preference-Applied`).

### 4. Validate payload semantics

Confirm the request/response body matches the spec's expectations for the chosen
media type: CRS handling, feature `id` semantics, property nullability, patch
semantics. See `references/media-types.md` (TODO: not yet written).

### 5. (Batch only) Apply Part 11 semantics

If the change involves multi-feature writes, decide **atomic vs batch** and follow
`references/part-11-transactions.md` (TODO: not yet written).

### 6. Verify against the spec

Cross-reference the concrete Requirement / Recommendation IDs from the spec (e.g.
`/req/create-replace-delete/post-op`) — do **not** paraphrase from memory. Cite the
requirement ID in the PR description or code comment.

### 7. Update contract tests

Add or update tests derived from the Abstract Test Suite (Annex A of each part) so
the change is covered.

## References

Reference files are built out incrementally as we work through the specs together.
Missing files mean "not yet written" — ask before assuming a topic is covered.

- [Conformance classes and URIs](./references/conformance-classes.md)
- [Part 4 — CRUD on features](./references/part-4-crud.md)
- Part 11 — Atomic and Batch Transactions (TODO: `references/part-11-transactions.md` not yet written)
- [HTTP semantics (status codes, headers)](./references/http-semantics.md)
- Media types and GeoJSON payload rules (TODO: `references/media-types.md` not yet written)

## Anti-patterns

- **Paraphrasing requirements.** Always quote or cite the requirement ID; the wording
  matters for conformance.
- **Skipping `/conformance` updates.** Adding a new capability without declaring its
  conformance URI breaks discovery.
- **Reusing `POST` for updates.** Part 4 uses `PUT` for full replace and `PATCH` for
  partial update — do not overload `POST`.
- **Silently changing feature `id`.** The server-assigned id on `POST` must be
  returned via `Location` header; existing ids are immutable on `PUT`/`PATCH`.
- **Batch = Atomic.** Part 11 distinguishes them: batch allows partial success,
  atomic is all-or-nothing. Do not conflate.
