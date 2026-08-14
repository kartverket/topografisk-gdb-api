.PHONY: docker-up docker-down docker-delete-db-volume docker-trivy-scan frontend-install frontend-build frontend-run frontend-lint frontend-format gcimport-install gcimport-test gcimport-run gccore-install gccore-test gccore-run gcjobs-install gcjobs-test gcjobs-run

DOCKER_COMPOSE := $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo 'docker compose')
DOCKER_SERVICES := geocomponents gcimport gccore gcjobs gcmapview
TRIVY_SERVICES := $(if $(SERVICE),$(SERVICE),$(DOCKER_SERVICES))
DOCKER_SOCKET ?= /var/run/docker.sock
TRIVY_IMAGE ?= aquasec/trivy:latest
TRIVY_CACHE_DIR ?= $(HOME)/.cache/trivy

docker-up:
	cd geocomponents && $(DOCKER_COMPOSE) up

docker-down:
	cd geocomponents && $(DOCKER_COMPOSE) down

docker-delete-db-volume:
	docker volume rm "geocomponents_pgdata"

docker-trivy-scan:
	@command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
	@[ -S "$(DOCKER_SOCKET)" ] || { echo "docker socket not found at $(DOCKER_SOCKET)"; exit 1; }
	@[ -z "$(SERVICE)" ] || echo " $(DOCKER_SERVICES) " | grep -Fq " $(SERVICE) " || { echo "unknown SERVICE '$(SERVICE)'; expected one of: $(DOCKER_SERVICES)"; exit 1; }
	@mkdir -p "$(TRIVY_CACHE_DIR)"
	@set -e; \
	for service in $(TRIVY_SERVICES); do \
		echo "Building $$service:scan"; \
		docker build -t "$$service:scan" "./$$service"; \
		echo "Scanning $$service:scan with Trivy in Docker"; \
		docker run --rm \
			-v "$(DOCKER_SOCKET):/var/run/docker.sock" \
			-v "$(TRIVY_CACHE_DIR):/root/.cache/trivy" \
			"$(TRIVY_IMAGE)" image \
			--format table \
			--exit-code 1 \
			--ignore-unfixed \
			--vuln-type os,library \
			--severity CRITICAL,HIGH \
			"$$service:scan"; \
	done

frontend-install:
	npm --prefix gcmapview install --ignore-scripts

frontend-build:
	npm --prefix gcmapview run build

frontend-run:
	npm --prefix gcmapview run dev

frontend-lint:
	npm --prefix gcmapview run lint

frontend-format:
	npm --prefix gcmapview run format

gcimport-install:
	uv sync --project gcimport

gcimport-test:
	cd gcimport && uv run pytest

gcimport-run:
	uv run --project gcimport uvicorn gcimport.app:app --port 8001

gccore-install:
	uv sync --project gccore

gccore-test:
	cd gccore && uv run pytest

gccore-run:
	uv run --project gccore gccore serve --port 8002

gcjobs-install:
	uv sync --project gcjobs

gcjobs-test:
	cd gcjobs && uv run pytest

gcjobs-run:
	uv run --project gcjobs gcjobs serve --port 8003
