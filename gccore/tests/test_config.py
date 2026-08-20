import pytest

from gccore import config


def test_alembic_directory_exists() -> None:
    assert config.alembic_dir().exists()
    assert config.alembic_dir().name == "alembic"


def test_redis_url_requires_environment(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        config.redis_url()


def test_redis_url_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/2")

    assert config.redis_url() == "redis://redis:6379/2"
