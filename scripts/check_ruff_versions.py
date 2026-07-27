#!/usr/bin/env python3
"""Fail if the ruff version pinned in .pre-commit-config.yaml and the one
pinned in geocomponents/pyproject.toml (dev group) disagree.

Both configs are the source of truth for different consumers (pre-commit /
CI vs. local `uv run ruff` / IDE), and drift between them silently produces
differing lint / format output. This pre-commit hook catches drift the
moment either file changes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

pc = (ROOT / ".pre-commit-config.yaml").read_text()
pc_match = re.search(r"astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?([\d.]+)", pc)
if not pc_match:
    sys.exit("could not find astral-sh/ruff-pre-commit rev in .pre-commit-config.yaml")

pp = (ROOT / "geocomponents/pyproject.toml").read_text()
pp_match = re.search(r'"ruff==([\d.]+)"', pp)
if not pp_match:
    sys.exit(
        "ruff must be exact-pinned in geocomponents/pyproject.toml dev deps "
        "as `ruff==X.Y.Z` so this check can compare it against .pre-commit-config.yaml"
    )

if pc_match.group(1) != pp_match.group(1):
    sys.exit(
        f"ruff version drift: .pre-commit-config.yaml={pc_match.group(1)}, "
        f"geocomponents/pyproject.toml={pp_match.group(1)}"
    )
