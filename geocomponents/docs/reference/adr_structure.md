# Architectural Decision Record (ADR) structure

ADRs help give an overview of decisions made and why. This document defines the format for new records; existing records retain the format they had when recorded.

## Organization and storage

ADRs are stored in `docs/adr`. Records are saved as markdown files sequentially named `xxxx-name_of_record.md` where `xxxx` increases sequentially and is not reused.

## ADR lifecycle

Any member of the team can propose an ADR.
The ADR is proposed through a pull request with `status` marked `proposed`, the team then reviews and either accepts/rejects it.
The ADR is merged after it is accepted/rejected.
If the ADR is accepted, its `status` is marked `accepted` with the date of acceptance.
If the ADR is rejected, its `status` is marked `rejected` with the date of rejection and the reason for rejection is recorded before merging.
If a decision is changed, the status of the ADR is marked `superseded by <superseding ADR>` (see [Changing an ADR](#changing-an-adr)).

## Content of an ADR

A record contains contains following fields:

- **Title**: Number and title.
Example: "1. Record architecture decisions".
- **Status**: See [ADR lifecycle](#adr-lifecycle).
Can be recorded retroactively.
Note this is the only field of an ADR that may semantically change once recorded.
- **Context**: Background for decision. Forces affecting decision such as technological, political and social are described along with their tensions if existing.
Neutral language.
- **Decision**: What decision was made referencing necessary documentation.
- **Alternatives and reason**: Why was this chosen over the alternatives?
- **Consequences**: What consequences follow from applying the decision, both good and bad.
- **Rejection reason**: Why the proposal was not accepted. Only added when a proposal was rejected.

## Changing an ADR

Once recorded, the content of an ADR is not changed. Typos/spelling might be fixed and broken links may be updated to the same target's new address, without changing its meaning.

If ADR `abcd-*` is superseded by ADR `wxyz-*`, the status of `abcd-*` should be marked `superseded by wxyz-*`.
