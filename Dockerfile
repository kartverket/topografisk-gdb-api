# Multi-stage Dockerfile for PostGIS API
# Build context is deployments/ (parent directory)
# Stage 1: Base image with dependencies
FROM python:3.12-slim AS base

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files (relative to deployments/)
COPY pyproject.toml uv.lock ./

# Install dependencies (this layer is cached unless lockfile changes)
ENV UV_PROJECT_ENVIRONMENT=/venv

RUN uv sync --frozen --no-dev

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy virtual environment from base stage
COPY --from=base /venv /venv

# Copy application code (relative to deployments/)
COPY app ./app

# Expose port
EXPOSE 8000

# Run the application directly from the virtual environment (no uv at runtime)
CMD ["/venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
