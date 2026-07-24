# topografisk-gdb-api

OGC APIs for topographic geodata, built on
[geocomponents](geocomponents/README.md): datasets are described in YAML, and
both the PostGIS schema and the per-dataset
[OGC API — Features](https://ogcapi.ogc.org/features/) services are generated
from those descriptions.

## Repository layout

- [`geocomponents/`](geocomponents/) — the engine. Start with its
  [README](geocomponents/README.md) for describing datasets and running
  locally; see [DEPLOY.md](geocomponents/DEPLOY.md) for deployment.
- [`nibio/`](nibio/) NIBIO AR5 database dump and schema adjustments. Useful for Postgis Topology integration.

## Development

The repo uses [pre-commit](https://pre-commit.com/) at the root to run various file-hygiene checks at commits.
The same hooks run in CI (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

`pre-commit` itself lives in the `geocomponents` dev dependency group, so
[uv](https://docs.astral.sh/uv/) is the only prerequisite:

```bash
# One-time setup: install the git hook and warm hook envs
uv sync --project geocomponents
uv run --project geocomponents pre-commit install

# Run against staged files (this is what the git hook does)
uv run --project geocomponents pre-commit run

# Run against every file in the repo (this is what CI does)
uv run --project geocomponents pre-commit run --all-files
```

For running the geocomponents test suite (unit tests without Docker,
contract + integration tests against a local PostGIS), see
[`geocomponents/README.md`](geocomponents/README.md#testing).
