from __future__ import annotations

import pytest

from gcimport.config import Settings


def test_from_env_reads_geocomponents_root_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GEOCOMPONENTS_API_URL",
        "http://topo-gdb-components.topo-gdb-components:8000/",
    )

    settings = Settings.from_env("http://localhost:8000")

    assert (
        settings.geocomponents_api_url
        == "http://topo-gdb-components.topo-gdb-components:8000"
    )


def test_from_env_requires_non_empty_geocomponents_root_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOCOMPONENTS_API_URL", "   ")

    with pytest.raises(ValueError, match="GEOCOMPONENTS_API_URL must not be empty"):
        Settings.from_env("http://localhost:8000")


def test_from_env_defaults_to_root_url() -> None:
    settings = Settings.from_env("http://localhost:8000")

    assert settings.geocomponents_api_url == "http://localhost:8000"