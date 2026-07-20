# HTTP Semantics for OGC API - Features Write Operations

Foundational vocabulary. Both Part 4 (CRUD) and Part 11 (Atomic and Batch
Transactions) build on the concepts here. When those references cite a status code,
header, or method property, this file is the ground truth.

**Base normative sources** (not OGC — plain HTTP/IETF):

- **RFC 9110** — HTTP Semantics (methods, status codes, headers, conditional
  requests, content negotiation). Supersedes RFC 7231, 7232, 7233, 7235.
  <https://www.rfc-editor.org/rfc/rfc9110>
- **RFC 9111** — HTTP Caching. <https://www.rfc-editor.org/rfc/rfc9111>
- **RFC 7240** — Prefer Header for HTTP. <https://www.rfc-editor.org/rfc/rfc7240>
- **RFC 9457** — Problem Details for HTTP APIs (supersedes RFC 7807).
  <https://www.rfc-editor.org/rfc/rfc9457>
- **RFC 7946** — GeoJSON media type (`application/geo+json`).
  <https://www.rfc-editor.org/rfc/rfc7946>
- **RFC 7396** — JSON Merge Patch. <https://www.rfc-editor.org/rfc/rfc7396>
- **RFC 6902** — JSON Patch. <https://www.rfc-editor.org/rfc/rfc6902>

The OGC specs generally point at RFC 9110's predecessors (RFCs 7231/7232) but the
semantics are unchanged; using RFC 9110 as the reference is safe.

---

## 0. Reading the specs — normative language

OGC standards use ISO/IEC Directives Part 2 conformance verbs. When reading spec
text, treat these as terms of art:

| Verb | Meaning |
|------|---------|
| **SHALL** / **SHALL NOT** | Absolute requirement / prohibition. Equivalent to IETF **MUST** / **MUST NOT**. |
| **SHOULD** / **SHOULD NOT** | Strong recommendation; deviation permitted only with justification. |
| **MAY** | Optional; either choice is conformant. |

Lowercase "must", "should", "may" are prose — **not normative**. Only the uppercase
forms bind conformance. If a clause does not use one of these uppercase verbs, it
is explanatory text; do not derive test cases from it.

OGC also assigns each normative statement a stable URI, categorised as:

| Prefix | Level | Example |
|--------|-------|---------|
| `/req/…`  | Requirement — SHALL-level. Tested by the Abstract Test Suite. | `/req/create-replace-delete/post-op` |
| `/rec/…`  | Recommendation — SHOULD-level. | `/rec/create-replace-delete/response-body` |
| `/per/…`  | Permission — MAY-level explicit allowance. | `/per/optimistic-locking-timestamps/ifunmodifiedsince-missing` |

When this skill's other references cite "the spec says X," they will use the URI
form above so the claim is unambiguous.

---

## 1. HTTP method properties

Three orthogonal properties from RFC 9110 §9.2. Every write endpoint decision hinges
on these.

| Property | Meaning | Client / server impact |
|----------|---------|------------------------|
| **Safe** | Method does not modify server state. `GET`, `HEAD`, `OPTIONS` are safe. | Caches, prefetchers, and crawlers may replay safe methods freely. |
| **Idempotent** | Repeating the request N times has the same effect on server state as doing it once. `GET`, `HEAD`, `PUT`, `DELETE`, `OPTIONS` are idempotent. `POST`, `PATCH` are **not** required to be. | Clients (and intermediaries) may safely retry idempotent methods on network failure. |
| **Cacheable** | Response may be stored and reused. `GET`, `HEAD` cacheable by default; `POST` cacheable only with explicit `Cache-Control`. | Governs whether `Cache-Control` / `ETag` on the response affect future requests. |

### 1.1 Methods used by Parts 4 & 11

| Method | Purpose in Features writes | Idempotent? | Body allowed? |
|--------|----------------------------|-------------|---------------|
| `POST` | Create one or many features; submit a transaction | No | Yes |
| `PUT` | Replace an existing feature in full | Yes | Yes |
| `PATCH` | Partial update of an existing feature | No (in general — depends on patch format) | Yes |
| `DELETE` | Remove a feature | Yes | Optional (rarely used) |

**Notes:**

- `PUT` semantics: the request body **replaces** the target resource. Any property
  omitted from the body is either cleared or set to server default — never carried
  over from the previous state. This is the key distinction from `PATCH`.
- `PATCH` idempotence depends on the patch format:
  - JSON Merge Patch (RFC 7396) is idempotent for a fixed target state.
  - JSON Patch (RFC 6902) with `test` / relative operations may not be.
  - Treat `PATCH` as **not** idempotent unless proven otherwise for your format.
- `DELETE` should be idempotent: deleting an already-deleted resource returns `404`
  or `410`, not an error state change. Repeated `DELETE`s must not do harm.

---

## 2. Content negotiation

RFC 9110 §12. Two directions matter for write operations.

### 2.1 Request body — `Content-Type`

Client declares the format of the request body. Server rejects unknown types with
`415 Unsupported Media Type` (§15.5.16).

Common media types for feature writes:

| Media type | Use |
|------------|-----|
| `application/geo+json` | GeoJSON Feature or FeatureCollection (RFC 7946). Preferred for create/replace. |
| `application/json` | Generic JSON; some servers accept it as a synonym for GeoJSON. |
| `application/merge-patch+json` | JSON Merge Patch body for `PATCH` (RFC 7396). |
| `application/json-patch+json` | JSON Patch body for `PATCH` (RFC 6902). |

### 2.2 Response body — `Accept` and `Content-Type`

Client's `Accept` header lists acceptable response types with quality values (`q=`).
Server responds with:

- `Content-Type` header matching what it produced.
- `406 Not Acceptable` (§15.5.7) if no representation matches. OGC APIs typically
  prefer to serve a default representation rather than 406.

Write responses may return the mutated resource (see `Prefer: return=representation`
below) or an empty body — the content negotiation still applies to whatever is
returned.

### 2.3 `Vary` header

If the response depends on request headers (`Accept`, `Accept-Language`,
`Prefer`, …), the server **should** emit `Vary: <header-list>` so caches key on
those inputs. Relevant for `/conformance` and `/collections` responses; less so for
individual write responses.

---

## 3. Status codes for write operations

Only codes actually reachable from Part 4 / Part 11 workflows. RFC 9110 §15.

### 3.1 2xx — Success

| Code | Meaning | When to use |
|------|---------|-------------|
| `200 OK` | Generic success with body | `PUT`/`PATCH` returning the updated feature; batch response with per-item status |
| `201 Created` | New resource created | `POST` that created one or more features. **Must** include `Location` header pointing at the new resource. |
| `204 No Content` | Success, no body | `PUT`/`PATCH` with `Prefer: return=minimal`; `DELETE` |

**`201` vs `200`:** Use `201` only when a new URI came into existence. A `PUT` that
replaces an existing feature returns `200` or `204`. A `PUT` that *creates* a
feature at a client-specified URI may return `201`.

### 3.2 3xx — Redirection

| Code | Meaning | When to use |
|------|---------|-------------|
| `303 See Other` | Refer client to a different URI to fetch the result | Some write flows point at the created resource. Rare in Features. |

### 3.3 4xx — Client error

| Code | Meaning | When to use |
|------|---------|-------------|
| `400 Bad Request` | Malformed request (invalid syntax, missing required fields) | Body is not valid JSON; required query parameter missing |
| `401 Unauthorized` | Missing or invalid authentication | — |
| `403 Forbidden` | Authenticated but not permitted | Read-only user hits `POST`; collection write-protected |
| `404 Not Found` | Target resource does not exist | `PUT`/`PATCH`/`DELETE` on unknown `featureId`; unknown `collectionId` |
| `405 Method Not Allowed` | HTTP method not supported on this URI | Read-only collection receives `POST`. **Must** include `Allow` header listing supported methods. |
| `406 Not Acceptable` | No representation matches `Accept` | See §2.2 |
| `409 Conflict` | Request conflicts with current state | Attempted create with duplicate id; concurrent modification detected without ETag |
| `410 Gone` | Resource existed but has been deleted permanently | Optional stronger form of `404` for known-deleted features |
| `412 Precondition Failed` | Conditional request precondition (`If-Match`, `If-Unmodified-Since`) failed | Lost-update protection triggered — see §5 |
| `413 Content Too Large` | Body exceeds server limit | Oversized batch upload |
| `415 Unsupported Media Type` | Server rejects the `Content-Type` | Client sent `text/xml` to a JSON-only endpoint |
| `422 Unprocessable Content` | Body parses and its media type is understood, but a semantic constraint is violated | Valid JSON that is not a valid GeoJSON Feature; a mandatory property is missing; polygon self-intersects; invalid CRS |
| `428 Precondition Required` | Server requires a conditional header | Server refuses unconditional `PUT`/`PATCH`/`DELETE` to force clients to use `If-Match` or `If-Unmodified-Since` |

**`400` vs `422`.** Both are explicitly documented in Part 4 and Part 11's core
status-code tables. The spec's own wording:

- `400` — "The server cannot or will not process the request due to an apparent
  client error" (syntax, malformed body, missing required parameter).
- `422` — "The server understands the content type of the request content and the
  syntax of the request content is correct but was unable to process the contained
  instructions. For example, the submitted resource does not meet a semantic
  constraint, e.g. a mandatory property is missing."

Use `400` when parsing fails; `422` when parsing succeeds but validation fails.

### 3.4 5xx — Server error

| Code | Meaning | When to use |
|------|---------|-------------|
| `500 Internal Server Error` | Unexpected server failure | Uncaught exception |
| `501 Not Implemented` | Method or capability not implemented | Server does not implement a declared conformance class |
| `503 Service Unavailable` | Temporary overload / maintenance | Include `Retry-After` header |

---

## 4. Required and useful headers

### 4.1 Request headers

| Header | Purpose |
|--------|---------|
| `Content-Type` | Media type of the request body (see §2.1). Required on any request with a body. |
| `Content-Length` | Byte length of the body. Usually set automatically. |
| `Accept` | Preferred response media type(s). |
| `If-Match` | Conditional write: proceed only if current `ETag` matches. Prevents lost updates. See §5. |
| `If-None-Match` | Conditional create: proceed only if resource does **not** exist. `If-None-Match: *` on `PUT` = "create only". |
| `If-Unmodified-Since` | Conditional write based on `Last-Modified` timestamp. Weaker than `If-Match`. |
| `Prefer` | Signal handling preferences. See §6. |

### 4.2 Response headers

| Header | Purpose |
|--------|---------|
| `Location` | URI of the newly created resource. **Required** with `201 Created`. On multi-feature create, may be omitted or point at the transaction. |
| `Content-Type` | Media type of the response body. Required whenever a body is present. |
| `Content-Language` | Language of the response body, if applicable. |
| `ETag` | Opaque validator for the resource's current state. Enables conditional updates. See §5. |
| `Last-Modified` | Timestamp of last change. Weaker validator than `ETag`. |
| `Allow` | List of methods valid for this URI. **Required** with `405 Method Not Allowed`. |
| `Retry-After` | Seconds (or HTTP-date) to wait before retrying. Use with `429`, `503`. |
| `Preference-Applied` | Echoes which `Prefer` tokens the server honored. See §6. |
| `Link` | Related resources (RFC 8288). Heavily used elsewhere in OGC APIs (`self`, `alternate`, `next`); on writes, may link to a created resource or a transaction status. |

---

## 5. Conditional requests (lost-update protection)

RFC 9110 §13. The single most important pattern for concurrent writes.

### 5.1 The problem

Two clients read the same feature at time T, both `PATCH` it at time T+1. Without
preconditions, the second write silently overwrites the first — a *lost update*.

### 5.2 The solution — strong ETags

1. On `GET`, the server returns an `ETag` header, e.g. `ETag: "abc123"`.
2. On subsequent `PUT` / `PATCH` / `DELETE`, the client sends
   `If-Match: "abc123"`.
3. If the current server-side `ETag` for that resource still equals `"abc123"`, the
   write proceeds and the response includes the **new** `ETag`.
4. If it has changed, the server returns `412 Precondition Failed` and the client
   must re-fetch, re-apply changes, and retry.

### 5.3 Strong vs weak ETags

- **Strong** (`"abc123"`): bit-identical representation required for match. Safe for
  `If-Match` on writes.
- **Weak** (`W/"abc123"`): semantically equivalent representations may share a weak
  ETag. **Not** valid for `If-Match` — use only for `If-None-Match` on `GET`.

### 5.4 `If-None-Match: *` for create-only PUT

`PUT /collections/{cid}/items/{fid}` with `If-None-Match: *`:

- If `{fid}` does not exist → create it, return `201`.
- If `{fid}` exists → `412 Precondition Failed`, do not overwrite.

Useful when the client generates the id and wants create-not-replace semantics.

### 5.5 `Last-Modified` / `If-Unmodified-Since`

Fallback when the server cannot compute a stable `ETag`. One-second resolution.
Vulnerable to rapid successive updates within the same second. Prefer `ETag` when
possible.

### 5.6 `428 Precondition Required`

Server-side enforcement of conditional writes. Introduced by
**RFC 6585** (subsequently folded into RFC 9110): the server refuses to process an
unconditional request and demands the client re-submit with a validator header.

**Spec status in OGC API - Features:** `428` is listed in the core status-code
tables of both Part 4 and Part 11. Part 4 also grants an explicit Permission
(`/per/optimistic-locking-timestamps/ifunmodifiedsince-missing`) covering the case
when `If-Unmodified-Since` is omitted from a write operation — in that case
the server **MAY**:

- **A.** respond with `428 (Precondition required)` (RFC 6585) or `409 (Conflict)`; or
- **B.** execute the operation and return a `2xx` status.

Either choice is conformant. Choose `428` when lost-update prevention is a hard
requirement (e.g., authoritative geodata); choose the permissive path only if the
underlying data model tolerates blind overwrites.

---

## 6. The `Prefer` header

RFC 7240. Client signals non-binding preferences. Server may honor or ignore; if
honored, it echoes via `Preference-Applied`.

### 6.1 `return`

| Token | Meaning |
|-------|---------|
| `return=representation` | Return the full resource in the response body after a write. Response includes the mutated feature, saving a round-trip. |
| `return=minimal` | Return an empty body (`204`) or a status stub. Reduces bandwidth. |

### 6.2 `handling`

| Token | Meaning |
|-------|---------|
| `handling=strict` | Reject the request on any warning-level issue (unknown properties, tolerated but non-preferred structure). |
| `handling=lenient` | Best-effort: apply what is understood, ignore or coerce the rest. |

Used in OGC batch/atomic transaction endpoints to decide whether an unknown
property in a Feature is an error (`422`) or silently dropped.

### 6.3 `respond-async`

Server processes the request asynchronously and returns `202 Accepted` with a
`Location` header pointing at a status resource. Relevant for large batch jobs.

### 6.4 Echoing preferences

RFC 7240 §3 states the server **SHOULD** include `Preference-Applied` in the
response when it honored one or more tokens:

```
Preference-Applied: return=representation, handling=strict
```

Absence means the server ignored them (or none applied). Because it is SHOULD-level,
clients cannot rely on its presence to detect honoring — they must still inspect
the response body or status to confirm.

---

## 7. Error response body — Problem Details

RFC 9457 (supersedes RFC 7807). The recommended standard shape for 4xx/5xx bodies.

**Media type:** `application/problem+json`.

**Minimum members:**

```json
{
  "type":     "https://example.org/errors/geometry-invalid",
  "title":    "Geometry is not valid",
  "status":   422,
  "detail":   "Polygon at features[3] is self-intersecting.",
  "instance": "/collections/roads/items?tx=42"
}
```

- `type` — a URI identifying the error class. If dereferenceable, should document
  the error. Use `about:blank` for generic errors and rely on `status`.
- `title` — short human-readable summary, stable for a given `type`.
- `status` — mirror of the HTTP status code.
- `detail` — human-readable explanation of *this* occurrence.
- `instance` — URI identifying the specific occurrence (often the request URI).

Extension members are allowed and encouraged for machine-consumable detail (e.g.
`errors: [ { pointer, code, message } ]` for per-item batch failures).

---

## 8. Quick decision cheatsheet

| Situation | Response |
|-----------|----------|
| Client sends body in a media type the endpoint doesn't understand | `415 Unsupported Media Type` |
| Body parses but the Feature is invalid GeoJSON | `422 Unprocessable Content` |
| `PUT`/`PATCH`/`DELETE` on unknown feature | `404 Not Found` |
| `PUT` with `If-Match` when ETag has changed | `412 Precondition Failed` |
| `PUT` with `If-None-Match: *` on an existing id | `412 Precondition Failed` |
| Successful `POST` creating one feature | `201 Created` + `Location` header |
| Successful `PUT` replacing an existing feature, client wants body | `200 OK` + `ETag` |
| Successful `PUT` replacing an existing feature, `Prefer: return=minimal` | `204 No Content` + `ETag` + `Preference-Applied` |
| Successful `DELETE` | `204 No Content` |
| Endpoint doesn't accept this method | `405 Method Not Allowed` + `Allow` header |
| Async batch accepted, still processing | `202 Accepted` + `Location` (status URI) + `Preference-Applied: respond-async` |

---

## Gaps to fill later

Items below are HTTP-adjacent but scoped out of this file. They belong in
future references:

- Concrete Part 4 requirement IDs mapped to the status codes in §3 — belongs in
  `part-4-crud.md`.
- Transaction-scoped `ETag` semantics, per-item error rollup, `respond-async`
  status resource shape — belongs in `part-11-transactions.md`.
- The full list of media types a server should advertise via `Accept` in
  `/conformance` and `/collections` — belongs in `media-types.md`.
- The exact `application/problem+json` extension shape used by OGC (if any is
  standardized) — needs verification against the current draft of *OGC API - Common*.
