# 2. Use uv for Python dependencies

Status: Accepted 2026-11-05 (recorded retroactively)

## Context

Python dependencies need to be installed consistently across development environments and CI.
The repository already used uv and committed a lockfile before geocomponents was introduced.

## Decision

We use uv to manage geocomponents' Python dependencies, declare them in `pyproject.toml`, and commit `uv.lock`.

## Alternatives and reason

Poetry was considered, but not evaluated in depth.
pip with a requirements file was another option.
A requirements file can pin exact versions, but pip does not provide an integrated project lockfile and sync workflow; without maintained pins, dependency versions can drift.
uv was chosen because it is fast and easy to use, while its committed lockfile helps keep development environments in sync.

## Consequences

Developers and CI can install dependencies from the same lockfile.
Dependency changes require updating and committing that lockfile.
Contributors need uv to follow the project's dependency workflow.
Other packages come with their own lockfiles, so CI and container images need coordinated uv versions and dependency setup across packages.
