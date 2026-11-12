# 7. One API per declared dataset

Status: Accepted 2026-11-10 (recorded retroactively)

## Context

We need to serve many datasets, each with its own collections and rules.
Dataset owners and users work with one dataset at a time and need to see which collections belong together.
Operations exposed through OGC API - Processes should run in a dataset's context, and planned transactions should make it clear which collections can be edited together.

## Decision

We give each declared dataset its own OGC API ([ADR 4](./0004_follow_ogc_api_standards.md)).
We list the datasets and their URLs at `/datasets`.

## Alternatives and reason

We could serve all collections under one OGC API root.
That would mix collections from different datasets, making it harder to discover which belong together.
Clients would need extra information to identify which collections can participate in a dataset-scoped transaction.
Dataset-specific processes would also be harder to discover and use: even a process shared by several datasets might need different parameters for each.

The `/datasets` index identifies each dataset as a resource, and a feature's URL identifies both its dataset and collection, making the resource hierarchy explicit.

A single root would let an OGC client discover every collection without knowing about `/datasets`.
However, that client would still need API-specific knowledge to group collections for transactions and to choose the right process and parameters.
We prefer an explicit dataset boundary over a single catalog that hides those distinctions.

## Consequences

Within a dataset's API, clients can discover its collections and available processes without sorting through those of other datasets.
The API root also provides a natural scope for dataset-wide transactions.

Clients that start without a dataset URL need to know about the project-specific `/datasets` index; an OGC client cannot use a single OGC API root to discover all collections.
We need to build and mount an OGC API for each dataset rather than exposing one combined API.
This adds some composition and routing work.
