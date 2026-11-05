# 5. Use PostGIS for spatial data

Status: Accepted 2026-11-05 (recorded retroactively)

## Context

Geocomponents needs a database for frequent updates to geographic features, spatial queries, and possible topology support.
Developers prefer open-source software, and there is organizational support for open-source and loosely coupled components.

## Decision

We use PostgreSQL with PostGIS to store and update geocomponents' spatial data.

## Alternatives and reason

We briefly considered column-oriented storage such as Parquet, along with Spark for processing.
We judged a row-oriented database better suited to frequent updates.
We briefly considered NoSQL databases, but judged a relational database a better fit for our structured data and its relationships.
We ruled out closed-source database systems because we prefer an open-source solution.

PostGIS supports spatial queries and has a topology extension.
PostGIS is also performant and widely used for geospatial work.
PostgreSQL functions also leave open the option of exposing database operations through PostgREST, which could give the database a separate HTTP interface without exposing its tables directly.

## Consequences

Geocomponents' schema generation and data access rely on PostgreSQL and PostGIS capabilities.
Developers and deployments need a PostGIS instance.
The database can handle spatial queries and support future topology work.
