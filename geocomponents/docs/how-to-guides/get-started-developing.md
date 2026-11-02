# Get started developing

Run these commands from the repository root.
You need Git, Python 3.12 or newer, and `uv`.
Install Docker with Compose if you plan to run database-backed tests.

Install the geocomponents development dependencies and the repository's commit hooks:

```bash
uv sync --project geocomponents --frozen
uv run --project geocomponents pre-commit install
```

The hooks use the configuration at the repository root and run when you commit.
To run them against all tracked files before committing, use:

```bash
uv run --project geocomponents pre-commit run --all-files
```

See [Run tests locally](run-tests-locally.md) for the test commands and database setup.
