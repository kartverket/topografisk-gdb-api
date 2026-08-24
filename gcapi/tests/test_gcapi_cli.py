from __future__ import annotations

from typer.testing import CliRunner

from gcapi.cli import app


def test_gcapi_exposes_serve_subcommand() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["serve", "--help"], prog_name="gcapi")

    assert result.exit_code == 0
    assert "Usage: gcapi serve [OPTIONS]" in result.stdout
