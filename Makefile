.PHONY: docker-up frontend-install frontend-build frontend-run gcimport-install gcimport-test gcimport-run

docker-up:
	cd geocomponents && docker compose up

docker-down:
	cd geocomponents && docker compose down

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
