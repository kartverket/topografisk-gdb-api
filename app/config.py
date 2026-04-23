"""
Configuration management using pydantic-settings.
Loads settings from environment variables with fallback defaults.

Two modes:
  Local dev:   set DATABASE_URL (or rely on individual POSTGRES_* defaults)
  Production:  set POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_DB,
               PGSSLCA, PGSSLCERT, PGSSLKEY (as in the Skiperator manifest)
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Option 1: full URL (takes priority when set)
    database_url: str | None = None

    # Development
    APP_ENV: str

    # Option 2: individual vars (Skiperator sets POSTGRES_* env vars)
    POSTGRES_DB: str = "geodata"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_USER: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # SSL certs — SKIP naming: PGSSLCA, PGSSLCERT, PGSSLKEY
    # These point to files mounted at /app/db-certs/ via filesFrom in the manifest
    PGSSLCA: str | None = None  # e.g. /app/db-certs/server.crt
    PGSSLCERT: str | None = None  # e.g. /app/db-certs/client.crt
    PGSSLKEY: str | None = None  # e.g. /app/db-certs/client.key

    # PAGINATION
    MAX_PAGE_SIZE: int = 1000

    @property
    def connection_url(self) -> str:
        if self.database_url:
            base = self.database_url
        else:
            base = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )
        if self.PGSSLCA:
            base += (
                f"?sslmode=require"
                f"&sslrootcert={self.PGSSLCA}"
                f"&sslcert={self.PGSSLCERT}"
                f"&sslkey={self.PGSSLKEY}"
            )
        return base

    class Config:
        env_file = ".env"


settings = Settings()
