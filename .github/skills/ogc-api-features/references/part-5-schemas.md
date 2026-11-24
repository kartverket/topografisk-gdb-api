# Part 5 — Schemas (also OGC API - Common - Part 3)

Source: [OGC editor's draft 23-058r3](https://docs.ogc.org/DRAFTS/23-058r3.html).
The linked draft is the source for exact requirements and conformance tests; conflicts within the draft are identified below rather than silently resolved here.

## 1. Scope

Part 5 describes logical schemas for geospatial collections, API building blocks for publishing those schemas, and [profiles](#term-profile) for references, codelists, and value domains.
A logical schema describes data independently of a particular feature encoding; it is not automatically a validation schema for every representation.

## 2. Conformance

Part 5 groups ten requirements classes by target type.
Each class defines rules, its conformance URI identifies the class, and the relevant Annex A tests assess conformance.
These identifiers use the OGC API - Common - Part 3 namespace.
Keep their spelling exact.

| Requirements class | Target type | Conformance class URI | Tests |
| -------------------- | ------------- | ----------------------- | ------- |
| [Schemas](#schemas-requirements) | Schema for a collection of geospatial data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/schemas` | A.1 |
| [Advanced property roles](#advanced-property-roles-requirements) | Schema for a collection of geospatial data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/advanced-property-roles` | A.2 |
| [References](#references-requirements) | Schema for a collection of data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/references` | A.3 |
| [Returnables and Receivables](#returnables-and-receivables-requirements) | Web API | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/returnables-and-receivables` | A.4 |
| [Queryables](#queryables-requirements) | Web API | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/queryables` | A.5 |
| [Sortables](#sortables-requirements) | Web API | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/sortables` | A.6 |
| [Profile query parameter](#profile-query-parameter-requirements) | Web API | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/profile-parameter` | A.7 |
| [Profiles for references](#profiles-for-references-requirements) | Collection of data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/profile-references` | A.8 |
| [Profiles for codelists](#profiles-for-codelists-requirements) | Schema for a collection of data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/profile-codelists` | A.9 |
| [Profiles for value domains](#profiles-for-value-domains-requirements) | Schema for a collection of data | `http://www.opengis.net/spec/ogcapi-common-3/1.0/conf/profile-domains` | A.10 |

The requirements class sections give `/req/…` identifiers; this table gives their corresponding `/conf/…` identifiers.
The target type identifies what a class assesses, not a separate `/conformance` endpoint for each collection or schema.
Target type alone does not determine declaration behavior: Annex A.1–A.3 inspect schemas without a declaration test, while A.4.1 requires the API's `/conformance` to include both `conf/schemas` and `conf/returnables-and-receivables`.
Other classes have their own declaration tests and dependencies in Annex A.
Selected tests are mentioned below, but this reference does not reproduce the complete Abstract Test Suite; consult the [draft's Annex A](https://docs.ogc.org/DRAFTS/23-058r3.html#ats) for full conformance procedures and dependencies.

## 3. References

The logical schema uses JSON Schema Draft 2020-12 as a data-description language; JSON Schema Core and Validation are normative references.
Simple Feature Access describes geometry types, while QUDT and UCUM provide unit vocabularies.
OGC API - Features Part 1 is a normative reference for the Abstract Test Suite only, not a dependency of the Part 5 requirements classes.

## 4. Terms used in Part 5

Terms relevant to the Part 5 requirements:

- <a id="term-logical-model"></a>**Logical model** — an abstract representation of domain knowledge from which physical artifacts can be generated.
- <a id="term-primary-geometry"></a>**Primary geometry** — the geometry the publisher considers a feature's most important spatial characteristic.
- <a id="term-primary-temporal-information"></a>**Primary temporal information** — the instant or interval the publisher considers a feature's most important temporal characteristic.
- <a id="term-profile"></a>**Profile** — additional constraints, conventions, or extensions associated with a representation beyond its media type.
- <a id="term-publisher"></a>**Publisher** — the entity responsible for making a resource available; it need not be the dataset owner.
- <a id="term-queryable"></a>**Queryable** — a property name that can be used in a filter expression.
- <a id="term-receivable"></a>**Receivable** — a property name that can be included when creating or updating a resource.
- <a id="term-returnable"></a>**Returnable** — a property name available when fetching a resource.
- <a id="term-sortable"></a>**Sortable** — a property name that can be used to sort resources of the same type.

## 5. Conventions

### 5.2. Identifiers

The base URI for partial requirement and conformance-test identifiers is `http://www.opengis.net/spec/ogcapi-common-3/1.0`.

### 5.3. Link relation types

| Relation | URI | Target |
| ---------- | ----- | -------- |
| `schema` | `http://www.opengis.net/def/rel/ogc/1.0/schema` | The collection's format-independent logical schema. |
| `queryables` | `http://www.opengis.net/def/rel/ogc/1.0/queryables` | Properties available for filtering. |
| `sortables` | `http://www.opengis.net/def/rel/ogc/1.0/sortables` | Properties available for sorting. |

These are OGC link relation types; the draft notes that they still need registration.
Use the IETF `describedby` relation instead when linking to a schema for validating a particular representation, such as a GeoJSON document.

## 6. Overview

### 6.1. Logical-schema vocabulary

JSON Schema describes the logical model independently of a particular data encoding.
To validate encoded data, convert the logical schema into a format-specific schema, such as JSON Schema for GeoJSON or JSON-FG, or XML Schema for GML.
Part 5 adds vocabulary for aspects of geospatial data not described by ordinary JSON Schema:

| Keyword | Describes |
| --------- | ----------- |
| `x-ogc-codelistUri` | The codelist referenced by a property. |
| `x-ogc-collectionId` | The target collection of a foreign-key reference. |
| `x-ogc-definition` | A property's semantic definition. |
| `x-ogc-nullValues` | Encoded values that represent null. |
| `x-ogc-propertySeq` | A property's relative position in the schema. |
| `x-ogc-role` | A property's role. |
| `x-ogc-unit` | A property's unit of measure. |
| `x-ogc-unitLang` | The vocabulary used for the unit of measure. |
| `x-ogc-uriTemplate` | A URI template for a referenced resource. |

### 6.2. Collection schema resources

| Resource | Purpose |
| ---------- | --------- |
| `/collections/{collectionId}/schema` | Logical schema for [returnable](#term-returnable) and [receivable](#term-receivable) properties. |
| `/collections/{collectionId}/queryables` | Properties available for filtering. |
| `/collections/{collectionId}/sortables` | Properties available for sorting. |

### 6.3. Profiles

A [profile](#term-profile) can vary a resource's representation within a media type without changing the resource's meaning.
Where supported, the `profile` query parameter requests one or more profiles; the server selects the applicable ones for the negotiated media type.
Part 5 specifies four profiles for schemas (codelists and value domains) and three for geospatial data (representations of references).

| Profile use | Representation choice |
|-------------|-----------------------|
| [References](#profiles-for-references-requirements) | Return a referenced resource as its ID, an HTTP(S) URI, or a link with an optional label. |
| [Codelists](#profiles-for-codelists-requirements) | Include code information in the schema or link to a codelist resource. |
| [Value domains](#profiles-for-value-domains-requirements) | Describe values permitted by the specification or values currently present in the dataset. |

<a id="schemas-requirements"></a>

## 7. Requirements Class "Schemas"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/schemas`.
The target is a schema for a collection of geospatial data, with JSON Schema Core as a dependency.

### 7.1. Schema representation

**Requirement 1 — `/req/schemas/json-schema`:**

- The schema SHALL be valid JSON Schema with `$schema` set to `https://json-schema.org/draft/2020-12/schema` and top-level `type` set to `object`.
- `$id` SHALL be an HTTP(S) URI without query parameters; requesting it with `Accept: application/schema+json` returns the schema.

**Requirement 2 — `/req/schemas/properties`:**

| Property | Required representation |
| ---------- | ------------------------- |
| Nonspatial | Include a `type` member. |
| Spatial | Omit both `type` and `$ref`; include `format: geometry-<type>` with the geometry type name in lowercase. |
| Temporal instant (also interval start/end) | A `string` with a format appropriate to its granularity, such as `date` or `date-time`. |
| Temporal interval | Either a `string` with `format: interval-iso8601` (two instants of the same granularity separated by `/`), or an array with `format: interval-array` containing two strings for start and end. |

Supported core Simple Feature geometry formats are `geometry-point`, `geometry-multipoint`, `geometry-linestring`, `geometry-multilinestring`, `geometry-polygon`, `geometry-multipolygon`, and `geometry-geometrycollection`.
The special formats are `geometry-any`, `geometry-point-or-multipoint`, `geometry-linestring-or-multilinestring`, and `geometry-polygon-or-multipolygon`.
The string `..` represents an unbounded interval end in either temporal-interval variant.
When the value type needs to be more specific than the JSON Schema `number`, `integer`, or `string` types, `format` SHALL be used.
A property applicable only to creation or updates SHALL include `writeOnly: true`; a property applicable only to fetched data SHALL include `readOnly: true`.

**Recommendation 1 — `/rec/schemas/properties`:**

- Provide a human-readable `title` for each property and a `description` where needed.
- Prefer `string`, `number`, `integer`, `boolean`, `object`, or `array` as the property `type`.
- Use `string` formats `uri`/`uri-reference`, `uri-template`, `uuid`, or `password` where applicable; numeric formats include `float`, `double`, `int32`, `int64`, `uint32`, and `uint64`.
- Prefer `format` values from JSON Schema, OpenAPI 3.1, or the OGC format register; the draft notes that the OGC format register has not yet been established.
- Describe applicable string and numeric constraints with `minLength`, `maxLength`, `enum`, `pattern`, `multipleOf`, `minimum`, `exclusiveMinimum`, `maximum`, or `exclusiveMaximum`.
- For integer enumerations other than codelists, provide `enum`; for string or integer codelist values, apply `codelist-inline` or `codelist-ref`.
- Use arrays of strings, numbers, or objects; list required properties in `required`.
- Limit JSON Schema keywords to those covered by the properties and additional-keyword provisions; avoid `$ref` by dereferencing reused schemas and representing them inline.

### 7.2. Additional keywords

#### 7.2.1. General rules

**Requirement 3 — `/req/schemas/additional-keywords`:** Additional keywords specified by OGC SHALL start with `x-ogc-`.
The draft cautions that later JSON Schema versions may restrict additional keywords.

#### 7.2.2. Properties with a specific role

**Requirement 4 — `/req/schemas/role`:** Declare a property's specific role with `x-ogc-role`, whose value SHALL be a string.

**Requirement 5 — `/req/schemas/role-id`:** A property with `x-ogc-role: id` SHALL identify its resource within its collection and have `type: string` or `type: integer`.
At most one property in a schema SHALL have this role.

#### 7.2.3. Ordering properties

**Requirement 6 — `/req/schemas/property-seq`:** `x-ogc-propertySeq` declares a hint for relative property order; its value SHALL be an integer specifying ascending order.

**Recommendation 2 — `/req/schemas/property-seq-unique`:** Values of `x-ogc-propertySeq` SHOULD be unique among properties of each object.
The draft labels this a recommendation but uses `/req/` in its identifier; keep that identifier unchanged.

#### 7.2.4. Unit of measure for numeric properties

**Requirement 7 — `/req/schemas/unit`:** `x-ogc-unit` declares a unit of measure and SHALL contain a string.
Unless `x-ogc-unitLang` names another unit language or register, its value SHALL use the case-sensitive UCUM `c/s` notation.
When UCUM is explicitly identified, `x-ogc-unitLang` SHALL be `UCUM`.
For a QUDT unit, `x-ogc-unitLang` SHALL be `QUDT` and `x-ogc-unit` SHALL be the URI of the unit.
The keyword applies when declaring a fixed unit; it does not require every numeric property to have a unit.

#### 7.2.5. Semantic definition of a property

**Requirement 8 — `/req/schemas/definition`:** `x-ogc-definition` identifies a property's semantic definition and SHALL be a URI.

#### 7.2.6. Special null values

**Requirement 9 — `/req/schemas/nullvalues`:** `x-ogc-nullValues` identifies data-type values treated as null despite being encoded as ordinary values.
It SHALL be an array of numbers or strings, matching the property's data type.

<a id="schemas-example"></a>

### 7.3. Example

The following illustrative building schema combines the §7 keywords, §8 property roles, a §9 resource reference, and the §15 `codelist-ref` profile in one place.
The surface is the primary geometry; a second point geometry can serve display or indexing needs.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://api.example.org/collections/buildings/schema",
  "type": "object",
  "title": "Buildings",
  "properties": {
    "id": {
      "type": "integer",
      "x-ogc-role": "id",
      "readOnly": true,
      "x-ogc-propertySeq": 1
    },
    "footprint": {
      "x-ogc-role": "primary-geometry",
      "format": "geometry-polygon-or-multipolygon",
      "x-ogc-propertySeq": 2
    },
    "representativePoint": {
      "format": "geometry-point",
      "x-ogc-propertySeq": 3
    },
    "observedAt": {
      "type": "string",
      "x-ogc-role": "primary-instant",
      "format": "date-time",
      "x-ogc-propertySeq": 4
    },
    "height": {
      "type": "number",
      "title": "Building height",
      "x-ogc-unit": "m",
      "x-ogc-unitLang": "UCUM",
      "x-ogc-definition": "https://example.org/definitions/building-height",
      "x-ogc-propertySeq": 5
    },
    "qualityCode": {
      "type": "integer",
      "enum": [-999999, 1, 2],
      "x-ogc-nullValues": [-999999],
      "x-ogc-propertySeq": 6
    },
    "featureKind": {
      "type": "string",
      "x-ogc-role": "type",
      "enum": ["building"],
      "x-ogc-propertySeq": 7
    },
    "parcelId": {
      "type": "string",
      "x-ogc-role": "reference",
      "x-ogc-collectionId": "parcels",
      "x-ogc-propertySeq": 8
    },
    "buildingUse": {
      "type": "string",
      "title": "Building use",
      "enum": ["residential", "commercial"],
      "x-ogc-codelistUri": "https://example.org/codelists/building-uses",
      "x-ogc-propertySeq": 9
    }
  },
  "required": ["footprint", "representativePoint", "observedAt", "featureKind"],
  "additionalProperties": false
}
```

The `api.example.org` and `example.org` URIs are illustrative; a deployed `$id` must resolve to this schema when requested with `Accept: application/schema+json`.
The root has `type: object`, while both spatial properties have a `format` but neither `type` nor `$ref`.
Only `footprint` has the `primary-geometry` role; the point's display or indexing use is an application decision, not a Part 5 property role.
The draft's Example 2 contains a trailing comma after its last `properties` member, so it is not valid JSON as printed.

<a id="advanced-property-roles-requirements"></a>

## 8. Requirements Class "Advanced property roles"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/advanced-property-roles`.
The target is a schema for a collection of geospatial data; this class depends on the [Schemas requirements class](#schemas-requirements).
These roles identify which spatial, temporal, or feature-type property to use when a data encoding has a distinguished position for that information.

### 8.1. Primary geometry

**Requirement 10 — `/req/advanced-property-roles/role-primary-geometry`:** A property with `x-ogc-role: primary-geometry` SHALL be spatial.
A schema SHALL have at most one property with this role.
If there is only one spatial property, it SHALL be the [primary geometry](#term-primary-geometry) even without an explicit role.
For multiple spatial properties, Annex A.2.1 expects an explicit `primary-geometry` role; it identifies the geometry mapped to a format's single geometry slot, such as GeoJSON's `geometry` member.
A single role in the schema cannot express a different primary geometry at different zoom levels.

### 8.2. Primary temporal information

**Requirement 11 — `/req/advanced-property-roles/role-primary-instant`:** A property with `x-ogc-role: primary-instant` SHALL be temporal, and a schema SHALL have at most one such property.
If there is only one temporal property, it SHALL be the [primary temporal information](#term-primary-temporal-information) even without this role.

| Requirement | Role | Constraint |
| ------------- | ------ | ------------ |
| 12 — `/req/advanced-property-roles/role-primary-interval-start` | `primary-interval-start` | Temporal property; at most one per schema. |
| 13 — `/req/advanced-property-roles/role-primary-interval-end` | `primary-interval-end` | Temporal property; at most one per schema. |
| 14 — `/req/advanced-property-roles/role-primary-interval` | `primary-interval` | Temporal property; at most one per schema. |

**Requirement 15 — `/req/advanced-property-roles/primary-temporal-constraints`:**

- `primary-instant` SHALL NOT be combined with any primary-interval role.
- `primary-interval` SHALL NOT be combined with `primary-instant`, `primary-interval-start`, or `primary-interval-end`.
- If both `primary-interval-start` and `primary-interval-end` exist, they SHALL have the same temporal granularity (`date` or `date-time`).
- If only the start or end role exists, the primary temporal information SHALL be the corresponding half-bounded interval.

### 8.3. Type

**Requirement 16 — `/req/advanced-property-roles/role-type`:** A property with `x-ogc-role: type` SHALL be a string property, and a schema SHALL have at most one such property.
This identifies a feature-type property; it is distinct from JSON Schema's `type` keyword.

### 8.4. Example

The [single schema example](#schemas-example) shows `primary-geometry`, `primary-instant`, and `type`.
With both a surface and a point property, the explicit `primary-geometry` role selects the surface; the point has no primary role.
Its instant role precludes adding a primary-interval role to the same schema.

<a id="references-requirements"></a>

## 9. Requirements Class "References"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/references`.
The target is a schema for a collection of data; this class depends on the [Schemas requirements class](#schemas-requirements).
A property with the `reference` role holds a foreign-key-like identifier of another resource, not another geometry on the same feature.
The role is available for reference properties; if used, the following requirements apply.

**Requirement 17 — `/req/references/role-reference`:**

- A property with `x-ogc-role: reference` SHALL have `type: string` or `type: integer`.
- If it is an integer, the referenced resource's property with `x-ogc-role: id` SHALL also be an integer.
- If all its values refer to geospatial data in one fixed collection on the same server, `x-ogc-collectionId` SHALL identify that collection.
- Otherwise, `x-ogc-uriTemplate` SHALL provide a URI template containing `{resourceId}`.

**Implementation recommendation, not an additional Requirement 17 constraint:** Also match the type of a string reference to the referenced collection's `id` property.
Requirement 17.B explicitly requires matching types only for integer references, but [Annex A.3.1](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_11) checks type equality for every reference with `x-ogc-collectionId`.

The [single schema example](#schemas-example) has `buildings.parcelId` targeting the separate `parcels` collection on the same server, just as the [draft's `accidents.roadSegment` example](https://docs.ogc.org/DRAFTS/23-058r3.html#example_9_1) targets `roadsegments`.
The fixed-collection condition applies to all values of the reference property; "same server" does not mean "same collection as the source".
Conflicting placeholder names in the draft: the overview table says `featureId`, while Requirement 17.D and Annex A.3.1 require `{resourceId}`; use `{resourceId}`.
The [draft's note](https://docs.ogc.org/DRAFTS/23-058r3.html#req_references_role-reference) that references to geospatial data in "different collections" are not covered conflicts with Requirement 17.C's fixed target collection (which can differ from the source) and 17.D's URI-template alternative.
The draft's `accidents.roadSegment` example also references `roadsegments`.
The scope intended by the note is unclear and is a candidate for OGC clarification; it does not negate fixed cross-collection references.

<a id="returnables-and-receivables-requirements"></a>

## 10. Requirements Class "Returnables and Receivables"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/returnables-and-receivables`.
The target is a Web API, with an indirect dependency on the [Schemas requirements class](#schemas-requirements).
The `/collections/{collectionId}/schema` resource describes the properties available when fetching data ([returnables](#term-returnable)) and those that can be supplied when creating or updating data ([receivables](#term-receivable)).
Properties applicable only in one direction carry `readOnly: true` or `writeOnly: true` as specified by Requirement 2.

**Requirement 18 — `/req/returnables-and-receivables/link`:** Every Collection resource SHALL link to its Returnables and Receivables resource with relation `http://www.opengis.net/def/rel/ogc/1.0/schema`.

**Requirement 19 — `/req/returnables-and-receivables/op`:** The schema resource SHALL support HTTP GET and the `application/schema+json` media type.

**Requirement 20 — `/req/returnables-and-receivables/response`:**

- A successful GET SHALL return HTTP `200`.
- A response with `Content-Type: application/schema+json` SHALL conform to the [Schemas requirements class](#schemas-requirements).
- `additionalProperties: false` SHALL disallow properties not declared in the schema; `additionalProperties: true` or omission (the default) SHALL allow them.

The [single schema example](#schemas-example) sets `additionalProperties: false`, so its declared properties form a closed set.

<a id="queryables-requirements"></a>

## 11. Requirements Class "Queryables"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/queryables`.
The target is a Web API, with an indirect dependency on the [Schemas requirements class](#schemas-requirements).
The [Annex A.5 conformance class](https://docs.ogc.org/DRAFTS/23-058r3.html#conf_queryables) additionally depends on OGC API - Features Part 1 GeoJSON and on Part 3 Filtering's "Queryables as Query Parameters" **or** "Features Filter" class.
These are conformance-test dependencies, distinct from the §11 requirements-class dependency.
The `/collections/{collectionId}/queryables` resource describes the names, types, and constraints of properties usable in filter expressions on the collection.
Its properties need not match the returnable or receivable properties in the [collection schema](#returnables-and-receivables-requirements): a publisher may expose a derived queryable or omit a content property from filtering.

**Requirement 21 — `/req/queryables/link`:** Every Collection resource SHALL link to its Queryables resource with relation `http://www.opengis.net/def/rel/ogc/1.0/queryables`.

**Requirement 22 — `/req/queryables/op`:** The Queryables resource SHALL support HTTP GET and the `application/schema+json` media type.

**Requirement 23 — `/req/queryables/response`:**

- A successful GET SHALL return HTTP `200`.
- A response with `Content-Type: application/schema+json` SHALL conform to the [Schemas requirements class](#schemas-requirements).
- If `additionalProperties` is absent or `true`, any property name is valid in a filter expression evaluated by the API; a reference to a property absent from a particular resource SHALL evaluate to `null`.
- If `additionalProperties: false`, a filter referencing a property not declared in the queryables schema SHALL receive HTTP `400`.

The `additionalProperties` rule here governs **filter property references**; [§10](#returnables-and-receivables-requirements) applies the same keyword to **properties in resource content**.
The [single schema example](#schemas-example) is a collection content schema, not a Queryables response; its `additionalProperties: false` does not by itself restrict filtering.
The draft's derived `common_band_names` queryable illustrates filtering values nested in STAC assets without exposing the underlying asset structure as queryable properties.
Filter languages may still reject unsupported predicates on a valid queryable, for example predicates on object-valued properties.
Example-versus-requirement conflict: the [draft's Queryables example](https://docs.ogc.org/DRAFTS/23-058r3.html#example_11_1) uses JSON Schema Draft 2019-09, while Requirement 1 requires Draft 2020-12 for Schemas, including Queryables responses conforming to that class.

<a id="sortables-requirements"></a>

## 12. Requirements Class "Sortables"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/sortables`.
The target is a Web API, with an indirect dependency on the [Schemas requirements class](#schemas-requirements).
The `/collections/{collectionId}/sortables` resource describes the names, types, and constraints of properties usable to sort resources in the collection.
As with [Queryables](#queryables-requirements), the publisher may expose sortable properties not directly present in the collection content schema or restrict sorting on content properties.

**Requirement 24 — `/req/sortables/link`:** Every Collection resource SHALL link to its Sortables resource with relation `http://www.opengis.net/def/rel/ogc/1.0/sortables`.

**Requirement 25 — `/req/sortables/op`:** The Sortables resource SHALL support HTTP GET and the `application/schema+json` media type.

**Requirement 26 — `/req/sortables/response`:**

- A successful GET SHALL return HTTP `200`.
- A response with `Content-Type: application/schema+json` SHALL conform to the [Schemas requirements class](#schemas-requirements).
- No property in the Sortables schema SHALL have `type: object` or `type: array`.
- No property in the Sortables schema SHALL be spatial.
- If `additionalProperties` is absent or `true`, any property name is valid in a sorting expression evaluated by the server; a reference to a property absent from a particular resource SHALL evaluate to `null`.
- If `additionalProperties: false`, a sorting expression referencing a property not declared in the Sortables schema SHALL receive HTTP `400`.

These are rules for **sorting expressions and Sortables properties**, not for the properties returned in resource content or permitted in filters.
The [single schema example](#schemas-example) describes content, including spatial properties; it is not itself a Sortables response.

<a id="profile-query-parameter-requirements"></a>

## 13. Requirements Class "Profile query parameter"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/profile-parameter`.
The target is a Web API.
The `profile` query parameter requests one or more profiles for a representation.

**Requirement 27 — `/req/profile-parameter/profile-param`:**

- GET on selected resources SHALL support an optional `profile` query parameter: an array of strings serialized in OpenAPI 3.1 `form` style with `explode: false` (comma-separated values).
- Each requested item SHALL be either a `profileId` from the OGC Profile Register (the value in `http://www.opengis.net/def/profile/OGC/0/{profileId}`) or an HTTP(S) URI of a profile.
- A profile URI need not be registered by OGC; communities can define their own.

**Permission 1 — `/per/profile-parameter/profile-param-default`:** The server MAY define a default value for `profile`.

**Permission 2 — `/per/profile-parameter/profiles-of-media-type`:** For each media type representing a resource, the server MAY support only a subset of the resource's profiles, including none.
After the media type is negotiated, the server selects the applicable profiles, if any, for that media type and resource.

**Recommendation 3 — `/rec/profile-parameter/profile-negotiation`:** If the server supports one or more requested profiles for the selected media type and resource, it SHOULD use those profiles in the response.
An unsupported requested profile SHOULD NOT cause an error during profile negotiation.

**Requirement 28 — `/req/profile-parameter/profile-param-response`:**

- Omitting `profile` in a request SHALL NOT cause an error.
- If the response media type supports web links in accordance with RFC 8288, the response SHALL link to the selected profile(s) using the `profile` link relation type.

**Recommendation 4 — `/rec/profile-parameter/profile-link-header`:** The response SHOULD also link to the selected profile(s) in its HTTP headers.
Conflicting expectations for valid but unsupported profiles: [Annex A.7.3](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_25) expects HTTP `400` for values outside the API's allowed list, while Recommendation 3 says unavailable requested profiles SHOULD NOT cause an error.
Conflicting support expectations: [Annex A.8.2](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_27), [A.9.2](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_32), and [A.10.2](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_34) test the named profiles and schema `profile` parameters despite Permission 2 allowing media-type subsets and Permissions 3–4 allowing a single schema profile or no schema `profile` parameter.
The conditions under which these tests apply need OGC clarification.

<a id="profiles-for-references-requirements"></a>

## 14. Requirements Class "Profiles for references"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/profile-references`.
The target is a collection of data, with indirect dependencies on [Returnables and Receivables](#returnables-and-receivables-requirements), the [Profile query parameter](#profile-query-parameter-requirements), and [References](#references-requirements).
The three profiles represent the same referenced resource as an identifier, a URI, or a link object.
The draft limits this class to simple cases and repeats the conflicting "different collections" note; see the [§9 conflict](#references-requirements).

**Requirement 29 — `/req/profile-references/ref-profiles`:** If the Returnables and Receivables schema contains a property with `x-ogc-role: reference`, GET operations on resources representing that collection's data SHALL provide the `profile` query parameter.
For features, this includes `/collections/{collectionId}/items` and `/collections/{collectionId}/items/{resourceId}`.

| Requirement and profile identifier | Representation of a reference in the response |
| ---------------------------------- | --------------------------------------------- |
| **30 — `/req/profile-references/rel-as-key`** (`http://www.opengis.net/def/profile/OGC/0/rel-as-key`) | If the reference property has `x-ogc-collectionId`, SHALL use the referenced resource's `resourceId` as a string or integer matching its identifier property's type. |
| **31 — `/req/profile-references/rel-as-uri`** (`http://www.opengis.net/def/profile/OGC/0/rel-as-uri`) | SHALL use an HTTP(S) URI of the referenced resource. |
| **32 — `/req/profile-references/rel-as-link`** (`http://www.opengis.net/def/profile/OGC/0/rel-as-link`) | SHALL use an object with `href` containing the referenced resource's URI; `title` is optional and supplies a human-readable label. |

For the [single building schema example](#schemas-example), the `parcelId` property has `x-ogc-collectionId: parcels`: `rel-as-key` can return `"P123"`, `rel-as-uri` can return `"https://api.example.org/collections/parcels/items/P123"`, and `rel-as-link` can return an object with that URI as `href` and an optional `title`.
These are alternative response representations of the same parcel reference, not additional properties in the logical schema.
The form of a link object depends on the media type; the draft notes that CSV and FlatGeobuf typically cannot adequately represent `rel-as-link`.
The selected profile is identified in the response as described in [§13](#profile-query-parameter-requirements).

**Recommendation 5 — `/rec/profile-references/default`:** If the server can provide meaningful link titles, the default `profile` value SHOULD include `rel-as-link`.

<a id="profiles-for-codelists-requirements"></a>

## 15. Requirements Class "Profiles for codelists"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/profile-codelists`.
The target is a schema for a collection of data; this class depends on the [Schemas requirements class](#schemas-requirements).
A codelist supplies definitions for string or integer codes, typically including human-readable labels.
The profiles describe two ways a schema can expose both the allowed codes and further information about them.

**Requirement 33 — `/req/profile-codelists/consistency`:** All codelist-valued properties in one schema SHALL use the same codelist profile.

**Recommendation 6 — `/rec/profile-codelists/profile-link-header`:** The schema response SHOULD link to the applied codelist profile in its HTTP headers.

**Requirement 34 — `/req/profile-codelists/codelist-inline`:** Under `codelist-inline` (`http://www.opengis.net/def/profile/OGC/0/codelist-inline`), each codelist-valued property's schema SHALL use `oneOf` with one subschema per code; each subschema SHALL include `const` with that code's value.

**Recommendation 7 — `/req/profile-codelists/codelist-inline-title`:** Each code's subschema SHOULD include a human-readable `title`.
The draft labels this a recommendation but uses `/req/` in its identifier.

**Requirement 35 — `/req/profile-codelists/codelist-ref`:** Under `codelist-ref` (`http://www.opengis.net/def/profile/OGC/0/codelist-ref`), each codelist SHALL be referenced by an HTTP(S) URI in `x-ogc-codelistUri`.
The profile's description represents the allowed codes with `enum`; Part 5 does not prescribe the representation served by the codelist URI.
The draft also permits `x-ogc-codelistUri` with `codelist-inline`, even though the code information is available inline.

**Permission 3 — `/rec/profile-codelists/options`:** A schema resource MAY support only one of these profiles.
If it supports more than one, either MAY be the default; the resource MAY support the [§13 `profile` query parameter](#profile-query-parameter-requirements) for clients to select a supported profile.
The draft labels this a permission but gives it a `/rec/` identifier.

The [single schema example](#schemas-example) uses `codelist-ref` for `buildingUse`, with `enum` for its codes and `x-ogc-codelistUri` for their definitions.
Its `qualityCode` and `featureKind` properties have ordinary `enum` constraints, not codelists.
An alternative `codelist-inline` representation would replace the `buildingUse` schema with `oneOf` entries containing `const` values and preferably `title` labels; the two profiles cannot be mixed for codelist-valued properties in one schema.
Identifier mismatch: [Annex A.9.2](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_32) uses plural `codelists-inline` and `codelists-ref` where Requirements 34–35 use singular `codelist-inline` and `codelist-ref`.
The Annex test excludes the combination of `enum` and `x-ogc-codelistUri` alongside inline `oneOf` values; it does not forbid `x-ogc-codelistUri` with inline values alone.

<a id="profiles-for-value-domains-requirements"></a>

## 16. Requirements Class "Profiles for value domains"

Requirements class URI: `http://www.opengis.net/spec/ogcapi-common-3/1.0/req/profile-domains`.
The target is a schema for a collection of data; this class depends on the [Schemas requirements class](#schemas-requirements).
The `valid-domain` profile describes values permitted by the underlying data specification; its domain is static unless that specification changes.
The `actual-domain` profile describes values present in the dataset at request time; it is a dynamic subset of the valid domain.
Unlike [codelist profiles](#profiles-for-codelists-requirements), which determine how codes and their definitions are represented, domain profiles determine which values the schema's constraint keywords describe.

| Property kind | Valid-domain constraints | Actual-domain constraints |
| ------------- | ------------------------ | ------------------------- |
| Text | `enum`, `pattern`, `minLength`, `maxLength` describe permitted values, patterns, and lengths. | `enum` contains values present in the dataset; length bounds reflect the observed range. |
| Numeric | `enum` for integers; `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, and `multipleOf` describe permitted values. | `enum` contains values present in the dataset; numeric bounds reflect the observed range. |
| Spatial | `format` describes permitted geometry types. | `format` reflects geometry types present in the dataset. |

Actual domains are useful for [Queryables](#queryables-requirements) and returnables to show what can be found or displayed in current data.
Determining actual domains requires examining current data and can therefore be expensive unless a good system for tracking and caching is in place.
Valid domains are important for [receivables](#returnables-and-receivables-requirements): values absent from the current dataset may still be accepted for new or updated resources.
Valid domains can typically be cached until the data specification changes.
Domain constraints are generally less useful for [Sortables](#sortables-requirements).

**Requirement 36 — `/req/profile-domains/consistency`:** All properties with constraint keywords in a schema SHALL use the same domain profile.

**Recommendation 8 — `/rec/profile-domains/profile-link-header`:** The schema response SHOULD link to the applied domain profile in its HTTP headers.

**Requirement 37 — `/req/profile-domains/actual-domain`:** When `actual-domain` (`http://www.opengis.net/def/profile/OGC/0/actual-domain`) is applied, the following SHALL be restricted to values present in the dataset at request time:

- Spatial `format` values starting with `geometry-`: the actual geometry types.
- `enum`: the actual property values.
- `minLength` and `maxLength`: the actual range of text lengths.
- `minimum`, `maximum`, `exclusiveMinimum`, and `exclusiveMaximum`: the actual numeric range.

**Permission 4 — `/rec/profile-domains/options`:** A schema resource MAY support only one domain profile.
If it supports more than one, either MAY be the default; the resource MAY support the [§13 `profile` query parameter](#profile-query-parameter-requirements) for clients to select a supported profile.
The draft labels this a permission but gives it a `/rec/` identifier.
The `valid-domain` URI (`http://www.opengis.net/def/profile/OGC/0/valid-domain`) appears in [Annex A.10.2](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_34), not in the §16 requirements.
Unlike `actual-domain`, `valid-domain` has no dedicated numbered requirement specifying its constraints.
Test-suite defects: [Annex A.10.3](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_35) repeats the `/conf/profile-domains/get-conformance` test ID from A.10.1; [A.10.4](https://docs.ogc.org/DRAFTS/23-058r3.html#_conformance_test_36) cites the undefined `/req/profile-domains/queryables-link` requirement.

In the [single building schema example](#schemas-example), `qualityCode` has an `enum` and `footprint` allows polygon or multipolygon.
If those are valid-domain constraints, an actual-domain representation could narrow them to the values and geometry types currently present.
The draft's Example 13 has missing commas and is not valid JSON as printed; it is not reproduced here.
