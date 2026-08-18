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

    settings = Settings.from_env()

    assert (
        settings.geocomponents_api_url
        == "http://topo-gdb-components.topo-gdb-components:8000"
    )


def test_from_env_requires_non_empty_geocomponents_root_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOCOMPONENTS_API_URL", "   ")

    with pytest.raises(ValueError, match="GEOCOMPONENTS_API_URL must be set"):
        Settings.from_env()


def test_from_env_requires_geocomponents_root_url() -> None:
    with pytest.raises(ValueError, match="GEOCOMPONENTS_API_URL must be set"):
        Settings.from_env()


def test_from_env_reads_upsert_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOCOMPONENTS_API_URL", "https://components.example")
    monkeypatch.setenv("GCIMPORT_UPSERT_BATCH_SIZE", "500")

    settings = Settings.from_env()

    assert settings.upsert_batch_size == 500


def test_from_env_requires_positive_upsert_batch_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEOCOMPONENTS_API_URL", "https://components.example")
    monkeypatch.setenv("GCIMPORT_UPSERT_BATCH_SIZE", "0")

    with pytest.raises(
        ValueError,
        match="GCIMPORT_UPSERT_BATCH_SIZE must be a positive integer",
    ):
        Settings.from_env()
