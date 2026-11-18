# 3. Use Ruff for Python linting and formatting

Status: Accepted 2026-11-05 (recorded retroactively)

## Context

The Python code needs consistent linting and formatting in development and CI.
Developers previously used different local formatting setups, and format-on-save produced diffs unrelated to the code being changed.
Ruff was introduced in the earlier codebase's lint workflow before geocomponents was added.

## Decision

We use Ruff for geocomponents' Python linting and formatting and declare its rules in `pyproject.toml`.

## Alternatives and reason

Flake8, Black and isort could provide these checks as separate tools.
Ruff was chosen because it combines their roles in one fast tool with less configuration to maintain.

## Consequences

Python linting and formatting share a tool and its configuration.
Contributors and CI need to use Ruff consistently.
The chosen rule set still needs to be maintained as the codebase evolves.
CI and pre-commit need compatible Ruff versions across packages, so upgrades require coordinating their pins and hooks.
