from gccore import config


def test_alembic_directory_exists() -> None:
    assert config.alembic_dir().exists()
    assert config.alembic_dir().name == "alembic"