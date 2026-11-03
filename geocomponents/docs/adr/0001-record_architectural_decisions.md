# 1. Record architecture decisions

Status: Accepted *2026-11-03*.

## Context

The project has a history of choices made.
The choices and their reasons currently lie with developers and hidden in git history.
On restructuring of the team, choices and their reasons might be forgotten.
Further, onboarding new members or hiring consultants require extra work because such choices are not clear.

Options that have been deliberately decided against are even less clear.

Having a log of decision records enables us to refer back to decisions made.
Such a log is different than standard documentation in that once a decision is made, it does not change.
Only whether we still apply the decision changes.
For this reason, the decision log fits better in a folder next to the other documentation.

## Decision

We record each architecture decision as an *Architectural Decision Record* (ADR) in `docs/adr`.
An ADR is first marked *proposed* and if the team approves it is marked *accepted* with date of acceptance.
A change of decision is a new ADR that supersedes it.
Once accepted, the content of an ADR is never edited, only typos, formatting, broken links and status can be changed.

See the [ADR structure reference](../reference/adr_structure.md) for the format of new records.
Later changes to that reference do not change the content or format of existing records.

## Alternatives and reason

The alternative to recording decisions it to not record them.
While this might save some time initially the downstream cost of not recording decisions is larger than the upfront cost of recording.
If decisions and their reasons are not recorded, any developer has to either accept or reject prior decisions without even knowing about them.
Recording why something was rejected can also save future time not spent discussing the same issue.

## Consequences

We will more easily be able to see decisions made here and what purpose they serve.
This serves different functions simultaneously:

1. It is easier to return and understand why a choice was originally made.
2. Onboarding new members will be easier.
3. We will not spend time discussing proposals already rejected.

Downside is that a larger portion of time will be spent writing ADRs instead of writing code and understanding tools.
An ADR can also give the perception of less flexibility in development but they can be superseded if deemed necessary.
