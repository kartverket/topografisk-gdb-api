# syntax=docker/dockerfile:1

FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app

COPY pyproject.toml README.md ./
RUN uv sync --no-dev --no-install-project

COPY src ./src
RUN uv sync --no-dev

FROM python:3.14-slim AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip \
	/usr/local/lib/python3.14/site-packages/pip-*.dist-info \
	/usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.14
RUN apt-get update \
	&& apt-get upgrade -y \
	&& rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 1000 gccore
USER gccore
EXPOSE 8000
ENTRYPOINT ["gccore"]
CMD ["serve"]
