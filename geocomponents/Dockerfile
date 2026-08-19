# syntax=docker/dockerfile:1

# ---- builder: resolve deps, install the package into a venv ----
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app

# Dependency layer — cached until pyproject/uv.lock change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Project layer — install geocomponents itself.
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---- runtime: slim, just the venv + src, non-root ----
FROM python:3.12-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
RUN apt-get update \
	&& apt-get upgrade -y \
	&& rm -rf /var/lib/apt/lists/*
RUN useradd -r -u 1000 geocomponents
USER geocomponents
EXPOSE 8000
ENTRYPOINT ["geocomponents"]
CMD ["serve"]
