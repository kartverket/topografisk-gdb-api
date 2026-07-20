# Part 4 — Create, Replace, Update, Delete

Reference for OGC API - Features Part 4 ("Create, Replace, Update and Delete").
Backend- and framework-agnostic. Cross-referenced by
[SKILL.md](../SKILL.md), [conformance-classes.md](./conformance-classes.md),
and [http-semantics.md](./http-semantics.md).

**Base namespace** for all `/req/…`, `/rec/…`, `/per/…` identifiers in Part 4:
`http://www.opengis.net/spec/ogcapi-features-4/1.0`. Every requirement ID below is
relative to this base.

**Section references** point at the local HTML copy in
`ogc-standards/Features_Part_4.html` with anchors for direct navigation.

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
  identifiers. This is one of two mechanisms for client-influenced IDs; the other
  is Permission 3 under §6.2 Response (POST body may include a suggested ID which
  the server MAY honor or ignore).

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
| [`/req/create-replace-delete/post-response`](https://docs.ogc.org/DRAFTS/20-002r1.html#req_create-replace-delete_post-response) | Req 6 (A/B/C) | §6.2.4 | (A) Success SHALL return `201`. (B) `201` SHALL include `Location` with the new resource URI. (C) Queued execution SHALL return `202`. |

† Spec HTML anchor uses `rec_` prefix even though the rule is a Requirement, not a
Recommendation. Reproduced as-is for click-through fidelity.

#### Perm 3 — client-suggested IDs

Two mechanisms let clients influence identifiers:

- **POST with ID in body** (Perm 3 above) — server MAY honor the client's
  suggestion or MAY ignore it. Server's decision wins.
- **PUT-to-create** (spec §6.3; see Scope) — client picks the URI directly;
  the collection's configuration decides whether the request succeeds.

#### Async CREATE (Req 6C) — fire-and-forget trap

> **⚠ `202` from POST is fire-and-forget.**
>
> When the server queues rather than executes, the client receives `202
> Accepted` and nothing else — no `Location`, no status URL, no callback.
> The spec explicitly says: *"the resource creation can succeed or fail,
> without further notification to the client about the result or the
> resource identifier."*
>
> Concrete traps:
>
> - **Clients that need to reference or retrieve the resource later cannot.**
>   They have no ID and no way to obtain one.
> - **Server-side validation failures are silent.** DB constraint violations,
>   schema rejections applied late, permission checks deferred to the queue
>   worker — none reach the client. Accepted-and-succeeded is
>   indistinguishable from accepted-and-rejected.
>
> Do not use Req 6C for interactive clients or when creation success matters.
> If queue-then-notify is required, use Part 11's asynchronous transactions
> (which define a status resource clients can poll).

#### Exceptions (spec §6.2.5)

Deferred to §6.1.1 HTTP status codes. See Overview.

<!-- Remaining subsections of this class to add in later chunks:
  - Replace (PUT /items/{id}) — spec §6.3
  - Delete (DELETE /items/{id}) — spec §6.4
  - OPTIONS — spec §6.5

  Remaining classes:
  - Update — spec §7
  - Optimistic Locking — spec §8
  - Features — spec §9

  Remaining top-level spec sections:
  - Media Types — spec §10
  - Security Considerations — spec §11
  - Abstract Test Suite — Annex A
-->
