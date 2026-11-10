# 6. Use declarative dataset descriptions

Status: Proposed (recorded retroactively)

## Context

We need to manage many geographic datasets, each with its own structure and validation rules.
Adding a dataset should take little manual work.
Dataset owners should be able to describe their data without requiring developers to know each dataset's structure in advance.

Many datasets of interest have UML models that contain structural information, and information about how data should be managed.
For example, in Felles kartdatabase (FKB), a feature's identity is found at `identifikasjon.lokalId`, and `avgrensesAv` relates a surface to the lines that border it.
Other datasets may express the same concepts differently.

Encoding these meanings implicitly in code makes it harder to add datasets with different structures.
Some rules are stated only in free text in dataset specifications.
Topology also imposes rules on how a dataset can be updated through an API and what bespoke functionality is useful.

We need a way to express the structure and rules of datasets both inside and outside FKB so that new datasets can be added without tailoring the implementation to each one.

## Decision

We use a human- and machine-readable dataset description as the single source of truth for generating a dataset's database and API.
The description defines the dataset's structure, validation rules for geometry, code lists and combinations of properties, and the dataset-specific update operations exposed through OGC API - Processes ([ADR 4](./0004_follow_ogc_api_standards.md)).

A dataset description works on its own and can also be derived from a UML model, enriched by a domain-knowledge document with rules that the UML model cannot currently express.
When derived from UML, it preserves the model's structure and names except where GeoJSON cannot represent them.

## Alternatives and reason

Using UML models directly would remove the need for a separate dataset description, but UML does not currently express all the rules we need.
Extending its use to cover those rules would take more development work and could make the models harder for dataset owners to use.

Another option is to infer domain knowledge from familiar names such as `avgrensesAv` and `identifikasjon.lokalId`.
That would require comparable work for each known pattern, exclude rules stated only in free text, and make it difficult for dataset owners to define or refine rules for other datasets.

NIBIO's declarative model is another option.
Their model has been used successfully for the datasets they maintain.
It uses PostGIS Topology as an engine, and we are not sure this is the right technology for all our datasets.
For example, two roofs can overlap in plan while remaining separate at different heights.
PostGIS Topology can split crossing edges at their projected intersection and assign a shared, interpolated Z coordinate, creating a boundary that does not exist in the dataset.
We also have a requirement of row-level transactional updates in the database which is not natively suited for PostGIS Topology.
NIBIO's solution also does not contain all the expressivity we need, so using it would still require substantial work and tie the rules to a concrete technology.

An explicit dataset description gives us room to express rules for many datasets rather than embedding them in one implementation.
Its domain language describes what the dataset requires without tying those rules to a particular database or topology engine.
Implementation-specific types in the description can be changed without redefining those domain rules.

## Consequences

Dataset owners gain a way to express the structure and rules of their data, and new datasets whose rules the description supports can gain a database and usable API with less manual configuration.
Deriving descriptions from UML means we must check that domain knowledge still applies when the UML model changes.
Recording which UML model version a description targets could make that check automatic and help prevent drift.
Changing an existing dataset may require mapping old fields to new ones and migrating stored data, but the explicit description can make those changes easier to identify than implicit rules in code.
We must identify and generalize rules, develop a language for describing them, and translate them into database and API behavior.
This takes more work up front than assuming existing rules in code.
The description must also remain expressive as we encounter datasets with new structures and validation needs.
