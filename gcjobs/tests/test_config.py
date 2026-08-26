import pytest

from gcjobs import config


def test_alembic_directory_exists() -> None:
    assert config.alembic_dir().exists()
    assert config.alembic_dir().name == "alembic"


def test_descriptions_dir_defaults_to_shared_repo_path(monkeypatch) -> None:
    monkeypatch.delenv("GEOCOMPONENTS_DESCRIPTIONS", raising=False)

    assert config.descriptions_dir().name == "descriptions"
    assert config.descriptions_dir().exists()


def test_descriptions_dir_reads_environment(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("GEOCOMPONENTS_DESCRIPTIONS", str(tmp_path))

    assert config.descriptions_dir() == tmp_path


def test_public_base_url_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("GCJOBS_BASE_URL", raising=False)

    assert config.public_base_url() == "http://localhost:8000"


def test_public_base_url_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("GCJOBS_BASE_URL", "https://jobs.example.no/")

    assert config.public_base_url() == "https://jobs.example.no"


def test_redis_url_requires_environment(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        config.redis_url()


def test_redis_url_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/2")

    assert config.redis_url() == "redis://redis:6379/2"


def test_gcimport_api_url_defaults_to_localhost(monkeypatch) -> None:
    monkeypatch.delenv("GCJOBS_IMPORT_API_URL", raising=False)

    assert config.gcimport_api_url() == "http://localhost:8001"


def test_gcimport_api_url_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("GCJOBS_IMPORT_API_URL", "http://gcimport:8000/")

    assert config.gcimport_api_url() == "http://gcimport:8000"


def test_max_upload_bytes_defaults_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("GCJOBS_MAX_UPLOAD_BYTES", raising=False)

    assert config.max_upload_bytes() == config.DEFAULT_MAX_UPLOAD_BYTES


def test_max_upload_bytes_reads_valid_override(monkeypatch) -> None:
    monkeypatch.setenv("GCJOBS_MAX_UPLOAD_BYTES", "4096")

    assert config.max_upload_bytes() == 4096


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [
        ("abc", "must be an integer"),
        ("0", "must be greater than zero"),
        ("-1", "must be greater than zero"),
    ],
)
def test_max_upload_bytes_rejects_invalid_values(
    monkeypatch, raw_value: str, message: str
) -> None:
    monkeypatch.setenv("GCJOBS_MAX_UPLOAD_BYTES", raw_value)

    with pytest.raises(RuntimeError, match=message):
        config.max_upload_bytes()
