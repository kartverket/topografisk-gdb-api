.PHONY: docker-up frontend-install frontend-build frontend-run gcimport-install gcimport-test gcimport-run gccore-install gccore-test gccore-run gcjobs-install gcjobs-test gcjobs-run

DOCKER_COMPOSE := $(shell command -v docker-compose >/dev/null 2>&1 && echo docker-compose || echo 'docker compose')

docker-up:
	cd geocomponents && $(DOCKER_COMPOSE) up

docker-down:
	cd geocomponents && $(DOCKER_COMPOSE) down

docker-delete-db-volume:
	docker volume rm "geocomponents_pgdata"

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
