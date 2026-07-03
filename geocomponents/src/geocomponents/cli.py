"""geocomponents command line: validate | apply-schema | serve.

This is the composition root for the running system. It wires the description
loader, the schema generator (DB seam), and the pygeoapi adapter (API seam) into
the gateway. It is the only place the concrete ``PygeoapiProvider`` is chosen;
swap it here to swap API frameworks.
"""

from __future__ import annotations

import typer

from . import config
from .descriptions.loader import DescriptionError, load_resolved_datasets

app = typer.Typer(add_completion=False, help="Description-driven geo components.")


@app.command()
def validate():
    """Load + validate every description; report collections found."""
    try:
        datasets = load_resolved_datasets(config.descriptions_dir())
    except DescriptionError as err:
        typer.secho(f"INVALID: {err}", fg="red")
        raise typer.Exit(code=1)
    for d in datasets:
        cols = ", ".join(c.name for c in d.collections)
        typer.secho(f"OK  {d.name}: [{cols}]", fg="green")
    typer.echo(f"{len(datasets)} dataset(s) valid.")


@app.command(name="apply-schema")
def apply_schema():
    """Create the dispatch layer, then each dataset's tables + functions."""
    import psycopg

    from .schema import functions, postgis
    from .schema.build import build_schema_plan

    datasets = load_resolved_datasets(config.descriptions_dir())
    with psycopg.connect(config.database_dsn()) as conn:
        functions.apply_dispatch(conn)
        typer.echo("applied dispatch layer (ogc.feature_*)")
        for d in datasets:
            plan = build_schema_plan(d)
            postgis.apply_tables(conn, plan)
            functions.apply_functions(conn, plan)
            typer.secho(
                f"applied schema '{d.name}' "
                f"({len(d.collections)} collection(s))",
                fg="green",
            )


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):
    """Build the gateway (one OGC API per dataset) and serve it."""
    import uvicorn

    from .api.pygeoapi_provider import PygeoapiProvider
    from .gateway.mounter import build_gateway

    datasets = load_resolved_datasets(config.descriptions_dir())
    provider = PygeoapiProvider(dsn=config.database_dsn())
    gateway = build_gateway(datasets, provider, base_url=config.public_base_url())
    typer.echo(f"serving {len(datasets)} dataset(s) at {config.public_base_url()}")
    uvicorn.run(gateway, host=host, port=port)


if __name__ == "__main__":
    app()
