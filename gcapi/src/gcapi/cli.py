from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, help="gcapi service commands.")


@app.callback()
def main() -> None:
    """Expose gcapi as a command group even when only one subcommand exists."""


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:  # noqa: S104
    import uvicorn

    uvicorn.run("gcapi.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
