# Part 4 — Create, Replace, Update, Delete

Reference for OGC API - Features Part 4 ("Create, Replace, Update and Delete").
Backend- and framework-agnostic. Cross-referenced by
[SKILL.md](../SKILL.md), [conformance-classes.md](./conformance-classes.md),
and [http-semantics.md](./http-semantics.md).

**Base namespace** for all `/req/…`, `/rec/…`, `/per/…` identifiers in Part 4:
`http://www.opengis.net/spec/ogcapi-features-4/1.0`. Every requirement ID below is
relative to this base.

**Section references** point at the canonical spec at
<https://docs.ogc.org/DRAFTS/20-002r1.html> (DRAFT, referenced as of 2026-07-22).

> **Two kinds of class dependency (spec §5.4).**
>
> - **Direct dependency** of X on Y: no Y ⇒ no X. A server cannot claim X without
>   also conforming to Y.
> - **Indirect dependency** of X on Y: some rules inside X have Y as a
>   precondition. No Y ⇒ those rules don't fire, but the server can still claim
>   X (the rules are vacuously satisfied).
>
> Direct dependencies appear as a *Dependency* row in each class overview table.
> Indirect dependencies are usually unlabelled — spotted by requirement text
> referencing something (e.g. `PUT`) defined by another class. Fleshed out with a
> real example in the Optimistic Locking section.

---

## Scope

Part 4 defines the behavior of a server that supports operations on **individual
resources** in a collection — add, replace, modify, delete. No side effects on
other resources; multi-resource ordering and atomicity are Part 11 territory.

Endpoint × method matrix (verbatim from spec §1 Table 1):

| Resource endpoint | POST | PUT | PATCH | DELETE |
|-------------------|------|-----|-------|--------|
| `/collections/{collectionId}/items` | create | n/a | n/a | n/a |
| `/collections/{collectionId}/items/{resourceId}` | n/a | replace (or **create**) | update | delete |

Two easy-to-miss subtleties:

- **`POST` at the `/items` endpoint** (the plural, *resources endpoint*) creates a
  new resource. The server assigns the identifier.
- **`PUT` at the `/items/{resourceId}` endpoint** (the singular, *resource
  endpoint*) can also create — but only if the collection accepts client-assigned
  identifiers. Both PUT-to-create (Perm 4, §6.3) and POST with a body-suggested
  ID (Perm 3, §6.2) can result in client-influenced identifiers; the mechanisms
  differ. See §6.2 and §6.3 for details.

---

## Terms

Four terms Part 4 adds on top of the Part 1 vocabulary. Quoted / trimmed from
spec §4.1.1–§4.1.4.

- **endpoint** — a web address (URI) at which access can be gained to a service or
  resource. (spec §4.1.1)
- **resources endpoint** (plural) — endpoint of the *set* of resource instances
  from a collection. For features:
  `{landingPageUri}/collections/{collectionId}/items`. (spec §4.1.2)
- **resource endpoint** (singular) — endpoint of a *specific instance* of a
  resource. For features:
  `{landingPageUri}/collections/{collectionId}/items/{featureId}`. (spec §4.1.3)
- **optimistic locking** — locking protocol that resolves change conflicts at the
  very last moment. Implemented via HTTP validator fields (`ETag`,
  `Last-Modified`) from the server and preconditions (`If-Match`,
  `If-Unmodified-Since`) from the client; see RFC 9110 §8.8. On validator
  mismatch the operation fails and the client must re-fetch and retry. (spec
  §4.1.4)

The plural/singular distinction of *resources endpoint* vs *resource endpoint*
matters — different URIs, different allowed methods (see Scope). Mixing them up
is a common source of `405 Method Not Allowed` bugs.

---

## Conventions

- **Spec §5.1 General remarks** points at OGC API - Features Part 1 Clauses 5 and
  6 for the base request/response conventions. Not restated here.
- **Spec §5.2 Identifiers** — all normative provisions in Part 4 are relative to
  the base URI given at the top of this file.
- **Spec §5.3 Sequence diagrams** — introduces tokens `<resources endpoint>` and
  `<resource endpoint>`; same distinction as the Terms glossary above.
- **Spec §5.4 Dependencies** — summarised in the preamble; concrete example in
  the Optimistic Locking section.

---

## Requirements Class: Create/Replace/Delete

Class URI: `req/create-replace-delete` (spec §6.1).

**Direct dependencies:**

- RFC 9110 (HTTP Semantics)

A server implementing this class supports adding, replacing, and/or removing
individual resources from a collection. Not all operations need to be
implemented for every mutable resource — the class permits any subset.

Method scope of this class:

- `POST` — add a new resource; identifier is server-assigned.
- `PUT` — replace an existing resource; MAY also create one (see Scope above).
- `DELETE` — remove a resource.

### Overview (spec §6.1)

#### The one class-level requirement

**Requirement 1** — `/req/core/methods` (spec §6.1)

> *A server SHALL implement one or more of the methods HTTP POST, PUT and/or
> DELETE for each mutable resource.*

Meaning: any subset is conformant. A server offering only `POST`-to-create
still conforms to this class.

#### HTTP status codes (spec §6.1.1)

Part 4 references standard HTTP status codes without redefining them. Their
meanings are RFC 9110 knowledge and out of scope for this file. For the codes
themselves see
[`http-semantics.md` §3](./http-semantics.md#3-status-codes-for-write-operations).

What is spec-relevant is the three-tier framing Part 4 imposes on them:

> **Three tiers (from spec §6.1.1 + Permission 1):**
>
> - **Normatively referenced** — `200`, `201`, `202`, `204`, `404`. These appear
>   in Part 4's requirement text. Per §6.1.1: *"support for some of these status
>   codes is mandatory for all compliant implementations"* — which subset a
>   given server must actually return depends on which requirements it is
>   subject to.
> - **Important and strongly encouraged** — the remainder of Table 3
>   (`400`, `401`, `403`, `405`, `406`, `412`, `413`, `415`, `422`, `428`,
>   `500`). Not called out normatively but *"strongly encouraged for both
>   client and server implementations."*
> - **Free** — Permission 1 (below) explicitly allows returning any other
>   registered HTTP status code beyond Table 3.

**Permission 1** — `/per/core/additional-status-codes` (spec §6.1.1)

> *Servers may support other capabilities of the HTTP protocol and therefore
> may return other status codes than those listed in Table 3.*

Guidance from §6.1.1: the API Description Document need not enumerate every
possible status code — clients must be prepared to receive codes not
documented there.

#### Cross-origin requests (spec §6.1.2)

Deferred to Part 1's *Support for cross-origin requests* clause. Part 4 adds
nothing new.

#### Schemas (spec §6.1.3)

Part 4 makes no assumption about schema constraints. Two server postures:

- **Schema-less** — servers backed by document stores or arbitrary storage.
  If the incoming feature is valid for the declared media type (e.g. valid
  GeoJSON), the resource should be created/updated with a `2xx` response.
- **Schema-enforcing** — servers backed by an RDBMS or another constrained
  store. To help clients avoid rejections, the server should publish schemas
  at `{landingPageUri}/collections/{collectionId}/schema` (endpoint defined
  by Part 1's Feature schemas clause).

<!-- TODO: extend this subsection with domain-model schema handling
     (FKB, AR5, SOSI, custom feature schemas). Current text is Part 4's
     minimum framing only. -->

#### Requirement IDs introduced in §6.1

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/core/methods`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_core_methods) | Requirement 1 | §6.1 | Server SHALL implement one or more of POST/PUT/DELETE per mutable resource. |
| [`/per/core/additional-status-codes`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_core_additional-status-codes) | Permission 1 | §6.1.1 | Server may return HTTP status codes beyond Table 3. |

#### Async execution (202) — fire-and-forget

When a server queues rather than immediately executes a write operation, it
SHALL return `202 Accepted`. This applies to POST (Req 6C), PUT (Req 10B),
and DELETE (Req 14B). In all cases:

- No further notification is sent to the client.
- The operation may succeed or fail silently.

Do not use async execution for interactive clients or when operation success
matters. For queue-then-notify, use Part 11's asynchronous transactions, which
define a status resource clients can poll.

POST-specific trap: `202` carries no `Location`
header and no identifier — the client has no way to retrieve the created
resource, and server-side validation failures (DB constraints, schema
rejections) are silent.

### §6.2: Create (POST /items)

The `POST` operation adds a new resource to a collection. Server assigns the
identifier and returns it via `Location`.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/create-replace-delete/post-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_post-op) | Req 2 (with Condition) | §6.2.2 | If server advertises POST via OPTIONS `Allow`, it SHALL support POST at the resources endpoint. |
| [`/req/create-replace-delete/post-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_create-replace-delete_post-body)† | Req 3 | §6.2.3 | POST body SHALL contain a resource representation. |
| [`/per/create-replace-delete/insert-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_insert-body) | Perm 2 | §6.2.3 | Server MAY support any resource encoding. |
| [`/req/create-replace-delete/post-content-type`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_create-replace-delete_post-content-type)† | Req 4 | §6.2.3 | `Content-Type` header SHALL declare the request body's media type. |
| [`/req/create-replace-delete/post-response-rid`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_post-response-rid) | Req 5 | §6.2.4 | On success, server SHALL assign a new, unique identifier. |
| [`/per/create-replace-delete/rid`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_rid) | Perm 3 | §6.2.4 | If POST body contains an ID, server MAY use it or ignore it. |
| [`/req/create-replace-delete/post-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_post-response) | Req 6 (A/B/C) | §6.2.4 | (A) Success SHALL return `201`. (B) `201` SHALL include `Location` with the new resource URI. (C) Queued execution SHALL return `202` — see §6.1 async execution; no `Location` or identifier is issued. |

† Spec HTML anchor uses `rec_` prefix even though the rule is a Requirement, not a
Recommendation. Reproduced as-is for click-through fidelity.

#### Perm 3 — client-suggested IDs

Two mechanisms let clients influence identifiers:

- **POST with ID in body** (Perm 3 above) — server MAY honor the client's
  suggestion or MAY ignore it. Server's decision wins.
- **PUT-to-create** (Perm 4, §6.3) — client picks the URI directly; any
  body-embedded identifier is ignored (Req 11). Whether PUT-to-create is
  supported is the server's choice (Perm 4).

#### Exceptions (spec §6.2.5)

Deferred to §6.1.1 HTTP status codes. See Overview.

### §6.3: Replace (PUT /items/{id})

The `PUT` operation replaces an existing resource at `<resource endpoint>`.
The identifier is determined by the request URI — not the body.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/create-replace-delete/put-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_put-op) | Req 7 (Condition + A) | §6.3.2 | Condition: OPTIONS `Allow` declares PUT. A) Server SHALL support PUT for every resource in the collection. |
| [`/per/create-replace-delete/put-create`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_put-create) | Perm 4 | §6.3.2 | Server MAY support PUT on a non-existing resource (PUT-to-create). |
| [`/req/create-replace-delete/put-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_create-replace-delete_put-body)† | Req 8 | §6.3.4 | PUT body SHALL contain a representation of the new resource content. |
| [`/per/create-replace-delete/update-put-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_update_put_body) | Perm 5 | §6.3.4 | Server MAY support any resource encoding. |
| [`/req/create-replace-delete/put-content-type`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_create-replace-delete_put-content-type)† | Req 9 | §6.3.4 | `Content-Type` header SHALL indicate the media type of the request body. |
| [`/req/create-replace-delete/put-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_put-response) | Req 10 (A/B) | §6.3.5 | A) Success SHALL be `200` or `204`. B) Queued execution SHALL return `202` — see §6.1 async execution. |
| [`/req/create-replace-delete/put-rid`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_put-rid) | Req 11 | §6.3.5 | If body contains a resource identifier, server SHALL ignore it. |
| [`/req/create-replace-delete/put-rid-exception`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_put-rid-exception) | Req 12 (A/B) | §6.3.6 | A) Target not found + server does not support PUT-create → SHALL return `404`. B) `If-Match` present + target not found → SHALL return `412`. |

† Spec HTML anchor uses `rec_` prefix even though the rule is a Requirement, not a
Recommendation. Reproduced as-is for click-through fidelity.

#### Perm 4 — PUT-to-create and body identifiers

PUT and POST handle client-supplied identifiers differently:

- **PUT** (Req 11): body identifier SHALL be **ignored**. URI is authoritative.
  No server discretion.
- **POST** (Perm 3, §6.2): body identifier MAY be honored or MAY be ignored.
  Server's choice.

See §6.2 (Perm 3) and Scope for the two mechanisms that let clients influence
identifiers. The collection-level advertisement flag for PUT-to-create
(`supportsNonAutogeneratedResourceIds`) is defined in the Features Requirements
Class — see §9.4.

#### If-Match as a replace guard (Perm 4 + Req 12B)

Perm 4 allows PUT to create a new resource. A client that needs a pure
replace — never a create — should send `If-Match`:

> *"The service MUST NOT treat an update request containing an If-Match header
> as an insert."* (spec §6.3.2, unnumbered normative prose)

Req 12B mandates `412` when `If-Match` is present and the resource does not
exist. Sending `If-Match: *` guarantees the server cannot silently create.

#### PUT is full replacement — partial body silently nullifies

`PUT` replaces the entire stored resource with whatever the body contains.
Properties absent from the body are treated as removed or set to null.
This is correct behaviour per the spec (Req 8), but produces silent data
loss if the client sends an incomplete representation:

- **Required fields**: a schema-enforcing server (see §6.1.3) will reject a
  PUT body missing required properties — `422` or `400`.
- **Optional fields with existing data**: schema validation cannot prevent
  omission. The server replaces the resource as sent; the data is gone with
  no error.

Safe patterns:
- **GET → modify → PUT**: round-trip to get the full current representation
  before replacing. Combine with `If-Match` (see above) to guard against
  concurrent writes.
- **PATCH** (§7): for field-level updates where the rest of the resource
  should be untouched.

#### Exceptions (spec §6.3.6)

Deferred to §6.1.1 HTTP status codes. See Overview.

### §6.4: Delete (DELETE /items/{id})

The `DELETE` operation removes a resource from a collection. No request body.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/create-replace-delete/delete-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_delete-op) | Req 13 (Condition + A) | §6.4.2 | Condition: OPTIONS `Allow` declares DELETE. A) Server SHALL support DELETE for every resource in the collection. |
| [`/req/create-replace-delete/delete-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_delete-response) | Req 14 (A/B) | §6.4.3 | A) Success SHALL be `200` or `204`. B) Queued execution SHALL return `202` — see §6.1 async execution. |
| [`/rec/delete/no-feature`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_delete_no-feature) | Rec 1 | §6.4.4 | If no resource with the identifier exists, response SHOULD be `404`. |

#### Rec 1 — 404 on missing resource

HTTP DELETE is idempotent (RFC 9110): repeating the call has the same effect
on server state. Idempotency is about *state*, not *status codes*. The spec
recommends `404` when the resource no longer exists — consistent with a client
that needs to distinguish "deleted successfully" from "was already gone".

#### Exceptions (spec §6.4.4)

Deferred to §6.1.1 HTTP status codes. See Overview.

### §6.5: Options (OPTIONS)

The `OPTIONS` operation declares which HTTP methods are available for a
resource endpoint. It is the mechanism behind the Condition clauses in
Reqs 2, 7, and 13 — those operations are only required when `OPTIONS`
has advertised the corresponding method in `Allow`.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/create-replace-delete/options-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_options-op) | Req 15 | §6.5.3 | Server SHALL support OPTIONS at each resource endpoint. |
| [`/per/create-replace-delete/options/req-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_options-req-body) | Perm 6 (A/B) | §6.5.4 | A) Request body MAY be included (format undefined by this Standard). B) Server MAY discard it. |
| [`/req/create-replace-delete/options-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_options-response) | Req 16 (A/B/C) | §6.5.5 | A) Success SHALL be `200`. B) `200` SHALL include `Allow`. C) `Allow` SHALL list methods permitted at the time and within the context of the request. |
| [`/per/options/other-methods`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_options_other-methods)‡ | Perm 7 | §6.5.5 | `Allow` MAY include any other relevant HTTP method (e.g. `GET`, `HEAD`). |
| [`/per/create-replace-delete/options/res-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_create-replace-delete_options-res-body) | Perm 8 | §6.5.5 | Response body MAY include content (format undefined by this Standard). |

‡ Perm 7's identifier uses the shorter namespace `/per/options/…` while
Perm 6 and 8 use `/per/create-replace-delete/options/…`. Reproduced as-is.

#### Req 16C — context-sensitive `Allow`

The `Allow` value is not a static server-level declaration. It reflects
which methods are permitted *at the time and within the context of the
request* — meaning it is user- and access-control-aware. The same endpoint
may return `Allow: GET, HEAD` for a read-only user and
`Allow: GET, HEAD, PUT, DELETE` for an editor.

#### Exceptions (spec §6.5.6)

Deferred to §6.1.1 HTTP status codes. See Overview.

## Requirements Class: Update

Class URI: `req/update` (spec §7.1).

**Direct dependency:**

- RFC 5789 (PATCH Method for HTTP)

A server implementing this class provides PATCH to modify parts of an existing
resource without transmitting a complete replacement. The spec does not mandate
a specific PATCH encoding.

### §7.1: Overview

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/update/methods`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_update_methods) | Req 17 | §7.1 | Server SHALL declare support for PATCH via OPTIONS. |

### §7.2: Update (PATCH /items/{id})

The `PATCH` operation modifies specific parts of an existing resource at
`<resource endpoint>`. The body is a change document, not a full replacement.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/update/update-patch-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_patch-update_update-patch-op)† | Req 18 | §7.2.2 | Server SHALL support PATCH for every resource in a collection. |
| [`/req/update/update-patch-body`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_patch-update_update-patch-body)† | Req 19 | §7.2.3 | Body SHALL contain a document describing the specific parts of the target resource to be modified. |
| [`/req/update/update-patch-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_patch-update_update-patch-response)† | Req 20 (A/B) | §7.2.4 | A) Success SHALL be `200` or `204`. B) Queued execution SHALL return `202` — see §6.1 async execution. |
| [`/req/update/rid`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_update_rid) | Req 21 | §7.2.4 | If body contains a resource identifier, server SHALL ignore it. |
| [`/rec/create-replace-delete/update/schema`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_update_patch_body-schema)‡ | Rec 2 | §7.3 | If server imposes schema constraints, SHOULD publish a schema (OAFeat-5). |

† HTML anchor uses `req_patch-update_` prefix; identifier uses `/req/update/`.
Reproduced as-is for click-through fidelity.

‡ Identifier namespace is `/rec/create-replace-delete/update/…` rather than
the class's own `/rec/update/…`. Reproduced as-is.

#### PATCH encoding is not mandated

Req 19 deliberately leaves the change-document format open — the spec only
requires that the body describes "the specific parts to be modified". The
server advertises which encodings it accepts via its API description. For
common PATCH encodings (JSON Merge Patch, JSON Patch) and their trade-offs,
see [`http-semantics.md`](./http-semantics.md). For encoding-specific
processing rules — including how JSON Merge Patch interacts with schema
validation and null values — see §9.7.

#### Exceptions (spec §7.2.5)

Deferred to §6.1.1 HTTP status codes. See Overview.

## §8: Optimistic Locking

§8 specifies two separate Requirements Classes for guarding against the
concurrent lost-update race condition (spec §8.1 Table 4). Two clients fetch
the same resource, both modify it, and the second write silently discards the
first. Optimistic locking prevents this by exchanging state tokens via HTTP
headers. For the header mechanics see
[`http-semantics.md` §5](./http-semantics.md#5-conditional-requests-lost-update-protection).

Two mechanisms, each its own Requirements Class:

### §8.1: Choosing between timestamps and ETags

From spec §8.1:

- **ETags** — derived from resource state; no separate metadata storage needed.
  Opaque and unforgeable: a client can only submit an ETag it actually received
  from a prior GET.
- **Last-Modified** — requires the server to store and maintain a change
  timestamp per resource. The spec recommends the client use the `Last-Modified`
  value from their most recent GET, but this is client-side guidance — the server
  cannot verify provenance. A client may submit any timestamp that passes the `≥`
  evaluation without having fetched the resource.

  *Note (not spec-derived):* In cooperative systems where clients genuinely do
  not want to overwrite concurrent changes, this bypass risk is theoretical —
  clients have no reason to forge a timestamp. In adversarial scenarios, write
  access is typically guarded by authentication and permissions regardless of
  optimistic locking, which remains the first line of defense.

- A server MAY implement both.

### Requirements Class: Optimistic Locking — Timestamps

Class URI: `req/optimistic-locking-timestamps` (spec §8.2).

No additional direct dependency listed; implicitly requires RFC 9110.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/optimistic-locking-timestamps/get-last-modified-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_last-modified-get-response) | Req 22 | §8.2.2 | GET response SHALL include `Last-Modified` representing when the resource was last modified. |
| [`/req/optimistic-locking-timestamps/put-last-modified-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_last-modified-put-response) | Req 23 | §8.2.2 | Successful PUT response SHALL include `Last-Modified`. |
| [`/req/optimistic-locking-timestamps/patch-last-modified-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_last-modified-patch-response) | Req 24 (Cond: Update) | §8.2.2 | Successful PATCH response SHALL include `Last-Modified`. |
| [`/req/optimistic-locking-timestamps/ifunmodifiedsince-put-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_ifunmodifiedsince-put-op) | Req 25 | §8.2.3 | PUT SHALL include `If-Unmodified-Since`. |
| [`/req/optimistic-locking-timestamps/ifunmodifiedsince-put-eval`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_ifunmodifiedsince-put-eval)† | Req 26 | §8.2.3 | `If-Unmodified-Since` SHALL be evaluated before PUT (RFC 9110 §13.1.4). |
| [`/req/optimistic-locking-timestamps/ifunmodifiedsince-patch-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_ifunmodifiedsince-patch-op) | Req 27 (Cond: Update) | §8.2.3 | PATCH SHALL include `If-Unmodified-Since`. |
| [`/req/optimistic-locking-timestamps/ifunmodifiedsince-patch-eval`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-timestamps_ifunmodifiedsince-patch-eval) | Req 28 (Cond: Update) | §8.2.3 | `If-Unmodified-Since` SHALL be evaluated before PATCH (RFC 9110 §13.1.4). |
| [`/per/optimistic-locking-timestamps/ifunmodifiedsince-missing`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_optimistic-locking-timestamps_ifunmodifiedsince-missing) | Perm 9 (Cond: header absent) | §8.2.3 | A) MAY respond `428` or `409`. B) MAY execute and return `2xx`. |

† Req 26 identifier reads `ifmatch-put-eval` — likely a copy-paste error; anchor
and content both refer to `If-Unmodified-Since`. Corrected in ID cell above;
anchor URL reproduces the spec as-is. Candidate for OGC errata.

#### Missing header behavior (Perm 9)

When `If-Unmodified-Since` is absent the spec leaves behavior open:

- **Strict** (Perm 9A): reject with `428 Precondition Required` or `409 Conflict`.
- **Lenient** (Perm 9B): execute the operation and return `2xx`.

The choice is a deployment decision. Strict is appropriate for collaborative
editing; lenient for single-writer or trusted-client scenarios.

### Requirements Class: Optimistic Locking — ETags

Class URI: `req/optimistic-locking-etags` (spec §8.3).

No additional direct dependency listed; implicitly requires RFC 9110.

#### Rules

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/optimistic-locking-etags/get-etag-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_get-etag-response) | Req 29 | §8.3.2 | GET response SHALL include `ETag` representing the resource state. |
| [`/req/optimistic-locking-etags/put-etag-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_put-etag-response) | Req 30 | §8.3.2 | Successful PUT response SHALL include `ETag`. |
| [`/req/optimistic-locking-etags/patch-etag-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_patch-etag-response) | Req 31 (Cond: Update) | §8.3.2 | Successful PATCH response SHALL include `ETag`. |
| [`/req/optimistic-locking-etags/ifmatch-put-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_ifmatch-put-op) | Req 32 | §8.3.3 | PUT SHALL include `If-Match`. |
| [`/req/optimistic-locking-etags/ifmatch-put-eval`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_ifmatch-put-eval) | Req 33 | §8.3.3 | `If-Match` SHALL be evaluated before PUT (RFC 9110 §13.1.1). |
| [`/req/optimistic-locking-etags/ifmatch-patch-op`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_ifmatch-patch-op)‡ | Req 34 (Cond: Update) | §8.3.3 | PATCH SHALL include `If-Match`. |
| [`/req/optimistic-locking-etags/ifmatch-patch-eval`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_optimistic-locking-etags_ifmatch-patch-eval) | Req 35 (Cond: Update) | §8.3.3 | `If-Match` SHALL be evaluated before PATCH (RFC 9110 §13.1.1). |
| [`/per/optimistic-locking-etags/ifmatch-missing`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_optimistic-locking-etags_ifmatch-missing)§ | Perm 10 (Cond: header absent) | §8.3.3 | A) MAY respond `428` or `409`. B) MAY execute and return `2xx`. |
| [`/per/optimistic-locking-etags/ifmatch-star`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_optimistic-locking-etags_ifmatch-star) | Perm 11 | §8.3.3 | Server MAY support `If-Match: *` to match any `ETag` value. |

‡ Req 34 spec text reads "A HTTP PUT operation that updates a resource" —
almost certainly a copy-paste error (Condition requires Update class; Req 32
already covers PUT-replace). Corrected to PATCH above. Candidate for OGC errata.

§ Perm 10 identifier reads `ifmatch-patch-op`; anchor reads `ifmatch-missing`.
Corrected to `ifmatch-missing` above. Candidate for OGC errata.

#### Strong ETags (spec §8.3.2)

Strong ETags require byte-for-byte identical response bytes for the same ETag
value (RFC 9110). For conformance with this Requirements Class the server MUST
produce deterministic feature representations:

- Property serialisation order must be stable.
- Link `href`, `rel`, and title values must be derived deterministically from
  resource/collection metadata.
- No dynamic per-request fields in the feature response body.

OGC API feature responses typically satisfy these constraints. A software
update that changes link titles or adds a new alternate encoding will invalidate
all existing ETags — clients receive `412` and must re-fetch. This is correct
and expected behaviour. Weak ETags (`W/"…"`) always fail `If-Match` evaluation
and cannot be used for optimistic locking. If deterministic serialisation cannot
be guaranteed, use the Timestamps class and do not claim conformance to this class.

*Note (not spec-derived):* In servers implementing CRS negotiation (Part 2),
coordinate values are CRS-specific, so the ETag is representation-specific.
JSON-FG (OGC Features and Geometries JSON) extends GeoJSON by including
`coordRefSys` in the response body; as long as that field and the coordinates
are serialised deterministically, two requests for the same resource in the
same CRS produce the same bytes and therefore the same ETag. In our view
there is no reason for a client to PUT in a different CRS than the one they
received — clients work in their chosen CRS, GET in that CRS, and PUT back
in the same CRS. This representation specificity may help prevent silent
coordinate-system errors. Whether to support PUT in a different CRS than the
GET is a server design decision not addressed by this spec.

#### Missing header behavior (Perm 10)

Same posture as Perm 9 in the Timestamps class: strict (`428`/`409`) or lenient
(`2xx`). Same deployment decision applies.

## Requirements Class: Features

Class URI: `req/features` (spec §9.1).

**Direct dependencies:**

- Requirements Class "Create/Replace/Delete" (§6)
- OGC API - Features - Part 1: Core, Requirements Class "Core"

**Conditional dependencies** (rules inside this class fire only when the named
class is also implemented):

- Part 1: GeoJSON Requirements Class
- Part 1: GML Simple Features Profile Level 0 and Level 2
- Requirements Class "Update" (§7)
- RFC 7396 (JSON Merge Patch)
- OGC API - Features - Part 2: Coordinate Reference Systems by Reference
- OGC API - Features - Part 5: Schemas, "Returnables and Receivables"

This class specialises the generic write operations of §6 and §7 for the
specific case where the resource type is a feature.

### §9.2–9.4: Endpoints and PUT-to-create flag

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/resources-endpoint`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_resources-endpoint) | Req 36 (A/B/C) | §9.2 | Items endpoint SHALL be `{landingPageUri}/collections/{collectionId}/items`; `collectionId` SHALL be each collection `id` with `itemType` feature or absent. |
| [`/req/features/resource-endpoint`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_resource_endpoint) | Req 37 (A/B/C/D) | §9.3 | Feature endpoint SHALL be `…/items/{featureId}`; `featureId` SHALL be a feature `id` previously obtained from a GET to the items endpoint. |
| [`/req/features/collection-endpoint`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_collection_endpoint) | Req 38 (A/B/C) | §9.4 | If server supports PUT-to-create, collection representation SHALL include `supportsNonAutogeneratedResourceIds: true` at `/collections` and `/collections/{collectionId}`. |

### §9.5: CRS handling — without Part 2

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/crs-crs84`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_crs-crs84) | Req 39 (A/B) | §9.5 | A) SHALL interpret all request-body geometries as CRS84 (2D) or CRS84h (3D). B) SHALL return an error if the request declares a different CRS. |

### §9.5: CRS handling — with Part 2

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/content-crs-header`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_content-crs-header) | Req 40 | §9.5 | SHALL inspect `Content-Crs` request header and interpret geometries in the declared CRS. |
| [`/req/features/default-crs`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_default-crs) | Req 41 (Cond: no CRS declared) | §9.5 | SHALL default to CRS84/CRS84h when request declares no CRS. |
| [`/req/features/crs-other-crs`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_crs-other-crs) | Req 42 (Cond: CRS declared; A/B) | §9.5 | A) SHALL interpret in declared CRS. B) SHALL return an error if declared CRS is unsupported for the collection. |
| [`/rec/features/crs-storage-crs`](https://docs.ogc.org/DRAFTS/20-002r1.html#rec_features_crs-storage-crs) | Rec 3 (A/B/C) | §9.5 | A) SHOULD declare `storageCrs` on mutable collections. B) SHOULD accept all CRSs listed in the collection's `crs` property. C) MAY limit writes to storage CRS only to avoid server-side coordinate conversion. |

### §9.6: Schema

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/schema`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_schema) | Req 43 (Cond: Part 5; A/B/C) | §9.6 | A) Schema SHALL be a JSON Schema at `…/{collectionId}/schema`. B) SHALL accept mutation requests where properties conform to the schema. C) SHALL NOT reject unknown properties unless schema declares `"additionalProperties": false`. |

### §9.7: JSON Merge Patch

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/update-json-merge-patch`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_update-json-merge-patch) | Req 44 (Cond: Update + Part 5 + advertises `application/merge-patch+json`; A/B/C/D) | §9.7 | A) SHALL process per RFC 7396. B) SHALL reject updates to the `x-ogc-role: id` property. C) SHALL treat spatial property updates as GeoJSON geometry objects. D) SHALL unset (remove) properties whose patch value is `null`. |
| [`/per/features/other-update-vocabularies`](https://docs.ogc.org/DRAFTS/20-002r1.html#per_features_other-update-vocabularies) | Perm 12 | §9.7 | Server MAY support other PATCH vocabularies in addition to or instead of RFC 7396 (e.g. JSON Patch RFC 6902, WFS 2.0 Update). |

#### Req 44D — null unsets and schema validation

Req 44D mandates RFC 7396 semantics: `null` in the patch body removes the
property from the stored resource entirely. This interacts with schema
validation (Req 43B):

- **Required properties**: applying the unset produces a feature missing a
  required field. Req 43B then rejects the result — `422`/`400`. JSON Merge
  Patch is therefore usable with strict schemas; `null` on a required field
  simply fails validation after the unset is applied.
- **Optional properties**: `null` removes any existing value. If the client's
  intent is to *preserve* a `null` value in a nullable optional property, RFC
  7396 cannot express that — `null` always means remove. JSON Patch (RFC 6902,
  `replace` operation with `null` value) can express the distinction. See also
  the TODO in [`http-semantics.md`](./http-semantics.md).

### §9.8: GeoJSON

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/geojson-create-replace`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_geojson-create-replace) | Req 45 (Cond: Part 1 GeoJSON + Part 5 + advertises `application/geo+json`; A/B) | §9.8 | A) REPLACE SHALL ignore the body `id` member, or reject if it differs from the URI featureId. B) `geometry` member SHALL map to the primary-geometry property. |

### §9.9: GML

| ID | Type | Spec § | Content |
|----|------|--------|---------|
| [`/req/features/gml-create-replace`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_gml-create-replace) | Req 46 (Cond: Part 1 GML + advertises `application/gml`) | §9.9 | REPLACE SHALL ignore `@gml:id`, or reject if it differs from the URI featureId. |
| [`/req/features/gml-srsname`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_features_gml-srsname) | Req 47 (Cond: Part 2 + GML content type; A/B) | §9.9 | A) SHALL inspect `srsName` attribute on each geometry element. B) `srsName` SHALL override `Content-Crs`. |

---

## §10: Media Types

§10 contains **no requirements**. It provides a **descriptive summary** of the media types that appear in Part 4's conformance classes. The table is thus illustrative rather than normative, listing the types defined by Part 4's conformance classes:

| Representation | CREATE / REPLACE | UPDATE (PATCH) | Schema documents |
|----------------|-----------------|----------------|-----------------|
| GeoJSON | `application/geo+json` | `application/merge-patch+json` | `application/schema+json` |
| GML | `application/gml+xml` | `application/xml` | `application/xml` |

This does not prohibit servers from supporting other encodings (e.g. `application/json-patch+json`)
— those simply fall outside Part 4's defined conformance classes.

<!-- Remaining top-level spec sections to add in later chunks:
  - Security Considerations — spec §11
  - Abstract Test Suite — Annex A
-->

---

## §11: Security Considerations

§11 contains **no requirements**. It defers to Part 1, Clause 11 and provides guidance and
examples only.

**Core premise:** write operations (POST, PUT, PATCH, DELETE) will in almost all cases be
access-controlled. Users making modifications need:

1. Authentication
2. Modification privileges on the collection / endpoint
3. Access to the relevant HTTP method on that resource

The OpenAPI definition should declare security schemes (global `security` member, or per-operation
overrides).

**Error responses — guidance only:**

| Situation | Typical response | Notes |
|-----------|-----------------|-------|
| No credentials supplied | `401 Unauthorized` | Response SHALL include `WWW-Authenticate` header with auth hints |
| Valid credentials, insufficient privileges | `403 Forbidden` | Body: `application/problem+json` |
| Server chooses to obscure | `401` or `404` | Server MAY return 401 for a valid-but-unprivileged user, or 404 to hide resource existence from unauthorised callers |

The 404 "stealth" option is explicitly acknowledged by the spec: if the user would not have
read access to the resource via GET either, returning 404 leaks no extra information.

<!-- Annex A (Abstract Test Suite) is a placeholder in the DRAFT spec —
     "will be added once the requirements classes and requirements are final."
     Revisit when the spec is published. -->