"""geocomponents command line: validate | apply-schema | serve.

This is the composition root for the running system. It wires the description
loader, the schema generator (DB seam), and the pygeoapi adapter (API seam) into
the gateway. It is the only place the concrete ``PygeoapiProvider`` is chosen;
swap it here to swap API frameworks.
"""

from __future__ import annotations

import typer

from geocomponents import config
from geocomponents.descriptions.loader import DescriptionError, load_resolved_datasets

app = typer.Typer(add_completion=False, help="Description-driven geo components.")


def _load_datasets():
    """Load the descriptions, or exit with a clear message.

    Fails when the folder is missing/empty (0 datasets) or when a
    description is invalid.
    """
    directory = config.descriptions_dir()
    try:
        datasets = load_resolved_datasets(directory)
    except DescriptionError as err:
        typer.secho(f"INVALID: {err}", fg="red")
        raise typer.Exit(code=1) from err
    if not datasets:
        typer.secho(
            f"No dataset descriptions found in '{directory}'. Point "
            "GEOCOMPONENTS_DESCRIPTIONS at a folder of dataset YAML files.",
            fg="red",
        )
        raise typer.Exit(code=1)
    return datasets


@app.command()
def validate():
    """Load + validate every description; report collections found."""
    datasets = _load_datasets()
    for d in datasets:
        cols = ", ".join(c.name for c in d.collections)
        typer.secho(f"OK  {d.name}: [{cols}]", fg="green")
    typer.echo(f"{len(datasets)} dataset(s) valid.")


@app.command(name="apply-schema")
def apply_schema():
    """Create the dispatch layer, then each dataset's tables + functions."""
    import psycopg

    from geocomponents.schema import functions, postgis
    from geocomponents.schema.build import build_schema_plan

    datasets = _load_datasets()
    with psycopg.connect(config.database_dsn()) as conn:
        functions.apply_event_schema(conn)
        typer.echo("applied feature event schema")
        functions.apply_topogdb(conn)
        typer.echo("applied topogdb schema")
        functions.apply_dispatch(conn)
        typer.echo("applied dispatch layer (ogc.feature_*)")
        for d in datasets:
            plan = build_schema_plan(d)
            postgis.apply_tables(conn, plan)
            functions.apply_functions(conn, plan)
            typer.secho(
                f"applied schema '{d.name}' ({len(d.collections)} collection(s))",
                fg="green",
            )


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000):  # noqa: S104 - intentional: bind all interfaces for containerised serving
    """Build the gateway (one OGC API per dataset) and serve it."""
    import uvicorn

    from geocomponents.api.pygeoapi_provider import PygeoapiProvider
    from geocomponents.events import (
        OutboxRelay,
        PostgresOutboxStore,
        RedisEventPublisher,
    )
    from geocomponents.gateway.mounter import build_gateway

    datasets = _load_datasets()
    dsn = config.database_dsn()
    provider = PygeoapiProvider(dsn=dsn)
    event_relay = OutboxRelay(
        PostgresOutboxStore(dsn),
        RedisEventPublisher(
            config.redis_url(),
            maxlen=config.event_stream_maxlen(),
        ),
        poll_seconds=config.event_poll_seconds(),
        batch_size=config.event_batch_size(),
        stale_after=config.event_claim_timeout_seconds(),
    )
    gateway = build_gateway(
        datasets,
        provider,
        base_url=config.public_base_url(),
        event_relay=event_relay,
    )
    typer.echo(f"serving {len(datasets)} dataset(s) at {config.public_base_url()}")
    uvicorn.run(gateway, host=host, port=port)


if __name__ == "__main__":
    app()
