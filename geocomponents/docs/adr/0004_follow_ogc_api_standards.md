# 4. Follow OGC API standards for the external interface

Status: Accepted, RECORD DATE AT MERGE (recorded retroactively)

## Context

Clients need a way to discover and work with geographic features.
We want a stable, easy-to-use interface for simple and topological features.
The organization favors open standards and wants transactional-style operations.
Users also want simpler topological edits: to split a surface, they should be able to send the splitting line rather than coordinate every feature-level change themselves.

## Decision

We follow OGC API - Features for the external feature interface and OGC API - Processes to expose dataset-specific operations.
We intend to follow OGC API - Features Part 11 for atomic multi-feature transactions when its draft interface is ready for use.

## Alternatives and reason

Alternatives included defining our own endpoints and using the older OGC WFS-T standard for transactional features.
WFS-T's XML-based interface was less familiar to the team than modern web APIs.
Following an open standard gives clients and developers a familiar way to understand and use the service without relying solely on project-specific documentation.
The newer OGC API standards also save us from designing feature and process endpoints from scratch.
Part 11's atomic transactions would let clients submit coordinated feature edits together, but the client must specify the changes.
Processes let us expose higher-level operations that accept simpler input and leave the necessary edits and topological consistency to the server.

## Consequences

Clients can build on established OGC API conventions.
Processes provide a standard way to expose custom operations, such as edits to topologically related features whose complexity the database handles.
Defining and building processes still takes work, but exposing them is easier.
The interface must be kept aligned with the parts of each standard it supports.
We can extend the interface where the standards permit it without changing their defined endpoint behavior.
