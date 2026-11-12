# 9. Use pygeoapi for the OGC API

Status: Proposed (recorded retroactively)

## Context

We follow OGC API - Features and OGC API - Processes ([ADR 4](./0004_follow_ogc_api_standards.md)) to expose our datasets.
The API must expose datasets described by our declarative model ([ADR 6](./0006-use_declarative_dataset_descriptions.md)) and read and write through public database functions ([ADR 8](./0008-api_db_components.md)).

## Decision

We use pygeoapi to implement geocomponents' OGC HTTP interface.

## Alternatives and reason

We could implement the OGC routes and responses ourselves with FastAPI.
That would give us control over the interface, but require us to build behavior already provided by pygeoapi, including discovery, links, conformance information and Processes endpoints.

`ldproxy`, `pg_featureserv` and `GoKoala` were considered as alternatives but `pygeoapi` has more integrations and the team is more comfortable working in python.
Other teams in the organization also use pygeoapi.

While pygeoapi's built-in database providers do not meet all the requirements of [ADR 6](./0006-use_declarative_dataset_descriptions.md), its support for custom providers lets us use our database functions without implementing the OGC interface ourselves.

## Consequences

Pygeoapi reduces the work needed to expose Features and Processes.
Pygeoapi's conformance does not by itself establish conformance of our interface: our custom providers and adaptations must also produce the required responses, such as valid GeoJSON for features and appropriate error responses.

We need to maintain custom data providers for our database functions.
We also need to extend pygeoapi to meet requirements it does not support.

Because each dataset has its own API ([ADR 7](./0007-one_api_per_dataset.md)), we need to build and mount a pygeoapi-backed app for each dataset rather than use its single global app.
These adaptations depend on pygeoapi's interfaces and need attention when it changes.
