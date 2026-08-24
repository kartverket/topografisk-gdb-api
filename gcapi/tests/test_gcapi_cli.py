from __future__ import annotations

import re

from typer.testing import CliRunner

from gcapi.cli import app

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def test_gcapi_exposes_serve_subcommand() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["serve", "--help"], prog_name="gcapi")
    stdout = ANSI_ESCAPE_RE.sub("", result.stdout)

    assert result.exit_code == 0
    assert re.search(r"Usage:\s+gcapi serve \[OPTIONS\]", stdout)
