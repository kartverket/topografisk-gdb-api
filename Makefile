.PHONY: docker-up docker-down docker-delete-db-volume docker-trivy-scan frontend-install frontend-build frontend-run frontend-lint frontend-format gcimport-install gcimport-test gcimport-run gccore-install gccore-test gccore-run gcjobs-install gcjobs-test gcjobs-run

DOCKER_COMPOSE := $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo 'docker compose')
DOCKER_SERVICES := geocomponents gcimport gccore gcjobs gcmapview
TRIVY_SERVICES := $(if $(SERVICE),$(SERVICE),$(DOCKER_SERVICES))
DOCKER_SOCKET ?= /var/run/docker.sock
TRIVY_IMAGE ?= aquasec/trivy:latest
TRIVY_CACHE_DIR ?= $(HOME)/.cache/trivy

docker-up:
	cd geocomponents && $(DOCKER_COMPOSE) up --build

docker-down:
	cd geocomponents && $(DOCKER_COMPOSE) down

docker-delete-db-volume:
	docker volume rm "geocomponents_pgdata"

docker-trivy-scan:
	@command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
	@docker version >/dev/null 2>&1 || { echo "docker daemon is not reachable"; exit 1; }
	@[ -z "$(SERVICE)" ] || echo " $(DOCKER_SERVICES) " | grep -Fq " $(SERVICE) " || { echo "unknown SERVICE '$(SERVICE)'; expected one of: $(DOCKER_SERVICES)"; exit 1; }
	@docker_host="$${DOCKER_HOST:-$$(docker context inspect "$${DOCKER_CONTEXT:-default}" --format '{{(index .Endpoints "docker").Host}}' 2>/dev/null)}"; \
	socket_path="$(DOCKER_SOCKET)"; \
	if [ -z "$$socket_path" ]; then \
		case "$$docker_host" in \
			unix://*) socket_path="$${docker_host#unix://}" ;; \
		esac; \
	fi; \
	if [ -n "$$docker_host" ] && [ -z "$$socket_path" ]; then \
		echo "docker-trivy-scan requires a unix socket Docker host; got '$$docker_host'"; exit 1; \
	fi; \
	[ -n "$$socket_path" ] || { echo "docker socket path could not be determined"; exit 1; }; \
	if [ ! -S "$$socket_path" ]; then \
		echo "warning: docker socket not directly visible at $$socket_path; continuing because docker CLI can reach the daemon"; \
	fi; \
	mkdir -p "$(TRIVY_CACHE_DIR)"; \
	set -e; \
	for service in $(TRIVY_SERVICES); do \
		echo "Building $$service:scan"; \
		docker build -t "$$service:scan" "./$$service"; \
		echo "Scanning $$service:scan with Trivy in Docker"; \
		docker run --rm \
			-v "$$socket_path:/var/run/docker.sock" \
			-v "$(TRIVY_CACHE_DIR):/root/.cache/trivy" \
			"$(TRIVY_IMAGE)" image \
			--format table \
			--exit-code 1 \
			--ignore-unfixed \
			--pkg-types os,library \
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
