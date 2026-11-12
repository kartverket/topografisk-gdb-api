# 8. Split API and database into separate components

Status: Proposed (recorded retroactively)

## Context

The organization wants loosely coupled components so that changes to storage or the API do not require rebuilding the whole service.
The dataset description is the source of truth ([ADR 6](./0006-use_declarative_dataset_descriptions.md)); the service should reflect its rules rather than constrain them to a particular API or table layout.
HTTP responses and links depend on the public API URL.

## Decision

We separate the database and API responsibilities behind public database functions.
The database stores features and handles data shaping, domain validation, geometry and writes.
The API calls those functions using dataset and collection identifiers from the description; it handles HTTP, OGC links and response envelopes.

We package and release both components together.
Their function contract can evolve as we develop them; independently packaging and versioning the components would require a new decision.

## Alternatives and reason

We could let the API read tables directly, and have it handle feature shaping and validation.
pygeoapi's built-in database providers are one such alternative and deliver much functionality out of the box.
They do not support some of our requirements, such as nested structures, so we would still need to write a custom provider.

With direct table access, the API would need to know the storage layout and implement dataset-specific read and write logic.
Changing tables or replacing the API technology would require coordinated changes across the API-database boundary.

We could put a separate data service between the API and database.
It would still need a defined contract and data-handling logic, but would add another layer without a current need.

Keeping data handling in the database we use the spatial and transactional capabilities of PostGIS ([ADR 5](./0005-use_postgis_for_spatial_data.md)).
The API can then focus on the external interface ([ADR 4](./0004_follow_ogc_api_standards.md)).
A later decision to build a processing middle layer can then take on these contracts if necessary.

Packaging and versioning the components independently would make a complete split.
While possible, that would require a more stable, explicitly versioned contract and a compatibility policy.
Packaging them together lets us change both sides and test them as a unit while the contract develops.

## Consequences

We need to construct functions for the API to read and write through directly.
The functions must be constructed in a way as to support the API's OGC operations.
The team must invest in PostGIS and PL/pgSQL expertise to maintain the data-handling functions.
The team needs to know the details of the relevant standards to design functions appropriately.
We also take on integration work that an out-of-the-box database provider would otherwise do.

Changes to one component need not depend on the other's internal workings, though replacing a technology still requires preserving or deliberately updating their shared contract.

We need good test coverage of the API-database boundary.

API and database are released and versioned together but technologies can still be switched.
Independent versioning remains possible if we later establish a stable contract and compatibility policy.
