"""Names accepted in dataset descriptions."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Annotated

from pydantic import AfterValidator

_NAME = re.compile(r"[A-Za-z_ÆØÅæøå][A-Za-z0-9_ÆØÅæøå]*\Z")
_MAX_NAME_BYTES = 40
PG_MAX_IDENTIFIER_BYTES = 63


def validate_name(name: str) -> str:
    if not _NAME.fullmatch(name) or len(name.encode("utf-8")) > _MAX_NAME_BYTES:
        raise ValueError(
            "name must start with a letter or underscore, contain only "
            "ASCII letters, digits, underscores or æøå, and fit in 40 UTF-8 bytes"
        )
    return name


LegalName = Annotated[str, AfterValidator(validate_name)]


def validate_unique_names(names: Iterable[str], *, where: str) -> None:
    seen: dict[str, str] = {}
    for name in names:
        previous = seen.get(name.casefold())
        if previous is not None:
            raise ValueError(f"{where}: names {previous!r} and {name!r} conflict")
        seen[name.casefold()] = name


def validate_generated_name(name: str) -> None:
    if len(name.encode("utf-8")) > PG_MAX_IDENTIFIER_BYTES:
        raise ValueError(f"generated PostgreSQL identifier {name!r} exceeds 63 bytes")
