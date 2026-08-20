"""Fail when shared container image version anchors drift.

The local compose stack started by `make docker-up` is the primary developer
entrypoint, so CI should use the same PostGIS image version. We also keep the
shared Python and uv helper image references aligned across the Python service
Dockerfiles to avoid silent environment drift between services.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def extract(pattern: str, relative_path: str, label: str) -> str:
    match = re.search(pattern, read_text(relative_path), re.MULTILINE)
    if not match:
        sys.exit(f"could not find {label} in {relative_path}")
    return match.group(1)


failures: list[str] = []

compose_postgis = extract(
    r"image:\s*imresamu/postgis:([^\s]+)",
    "geocomponents/docker-compose.yml",
    "compose PostGIS image",
)
ci_postgis = extract(
    r"services:\s*\n\s*db:\s*\n\s*image:\s*imresamu/postgis:([^\s]+)",
    ".github/workflows/ci.yml",
    "CI PostGIS image",
)
if compose_postgis != ci_postgis:
    failures.append(
        "PostGIS mismatch: "
        f"geocomponents/docker-compose.yml={compose_postgis}, "
        f".github/workflows/ci.yml={ci_postgis}"
    )

python_dockerfiles = (
    "geocomponents/Dockerfile",
    "gccore/Dockerfile",
    "gcimport/Dockerfile",
    "gcjobs/Dockerfile",
)

reference_python = extract(
    r"FROM\s+python:([^\s]+)\s+AS\s+builder",
    python_dockerfiles[0],
    "reference Python builder image",
)
reference_uv = extract(
    r"COPY\s+--from=ghcr\.io/astral-sh/uv:([^\s]+)\s+/uv\s+/usr/local/bin/uv",
    python_dockerfiles[0],
    "reference uv helper image",
)

for relative_path in python_dockerfiles:
    builder_python = extract(
        r"FROM\s+python:([^\s]+)\s+AS\s+builder",
        relative_path,
        "Python builder image",
    )
    runtime_python = extract(
        r"FROM\s+python:([^\s]+)\s+AS\s+runtime",
        relative_path,
        "Python runtime image",
    )
    uv_image = extract(
        r"COPY\s+--from=ghcr\.io/astral-sh/uv:([^\s]+)\s+/uv\s+/usr/local/bin/uv",
        relative_path,
        "uv helper image",
    )

    if builder_python != runtime_python:
        failures.append(
            f"{relative_path}: python builder {builder_python} != runtime {runtime_python}"
        )
    if builder_python != reference_python:
        failures.append(
            f"{relative_path}: python base {builder_python} != reference {reference_python}"
        )
    if uv_image != reference_uv:
        failures.append(
            f"{relative_path}: uv helper {uv_image} != reference {reference_uv}"
        )

node_builder = extract(
    r"FROM\s+node:([^\s]+)\s+AS\s+builder",
    "gcmapview/Dockerfile",
    "Node builder image",
)
node_runtime = extract(
    r"FROM\s+node:([^\s]+)\s+AS\s+runtime",
    "gcmapview/Dockerfile",
    "Node runtime image",
)
if node_builder != node_runtime:
    failures.append(
        f"gcmapview/Dockerfile: node builder {node_builder} != runtime {node_runtime}"
    )

if failures:
    sys.exit("container image / uv version drift:\n- " + "\n- ".join(failures))
