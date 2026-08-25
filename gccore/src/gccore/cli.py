from __future__ import annotations

import typer
from alembic import command
from alembic.config import Config

from gccore import config

app = typer.Typer(add_completion=False, help="gccore service commands.")


def _escape_alembic_config_value(value: str) -> str:
    return value.replace("%", "%%")


def alembic_config() -> Config:
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(config.alembic_dir()))
    alembic_cfg.set_main_option(
        "sqlalchemy.url", _escape_alembic_config_value(config.sqlalchemy_url())
    )
    alembic_cfg.set_main_option("version_table_schema", config.DB_SCHEMA)
    return alembic_cfg


@app.command(name="migrate-db")
def migrate_db(revision: str = "head") -> None:
    command.upgrade(alembic_config(), revision)


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000) -> None:  # noqa: S104
    import uvicorn

    uvicorn.run("gccore.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
