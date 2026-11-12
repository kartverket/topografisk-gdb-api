# 10. Organize geocomponents documentation with Diátaxis

Status: Proposed (recorded retroactively)

Introduced in [ba8da15](https://github.com/kartverket/topografisk-gdb-api/commit/ba8da15).

## Context

Geocomponents documentation covered getting started, deployment, concepts and detailed descriptions in a long README and a separate deployment document.
It was difficult to see what geocomponents covered and what it lacked, and to onboard developers.
For a non-developer, the documentation was not usable.

The project will need to onboard new developers, and data owners may want to see how datasets can be described and published as the project develops.

Clear documentation is essential to onboard developers, help developers build web clients and help dataset owners understand which needs are met.

## Decision

We organize geocomponents documentation according to [Diátaxis](https://diataxis.fr/): tutorials, how-to guides, reference and explanation.
Architecture decision records are maintained separately.

## Alternatives and reason

We could keep the README and deployment document organized by topic, with improved headings and links.
That would avoid splitting the existing documents, but still mix material for learning, completing a task, looking up details and understanding concepts.
This would still require substantial effort without separating the different reader needs.
Keeping mixed-purpose material in one document would also make it harder to maintain.

Diátaxis provides a structure based on what readers need from a document, which fits the different ways people use geocomponents documentation.
Smaller, focused pages make it easier to find and communicate the relevant information to developers and non-developers.
They may also be more likely to stay current than a long document covering many topics.
We did not compare other documentation frameworks in detail.

## Consequences

Readers can navigate to material suited to their purpose, and contributors have a clearer place to add or update information.
We must decide where content belongs, split mixed-purpose material and maintain navigation and links between pages.
We need to ensure that the documentation stays up to date over many focused pages.
