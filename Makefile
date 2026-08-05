.PHONY: docker-up frontend-install frontend-build frontend-run gcimport-install gcimport-test gcimport-run

docker-up:
	cd geocomponents && docker compose up

frontend-install:
	npm --prefix gcmapview install --ignore-scripts

frontend-build:
	npm --prefix gcmapview run build

frontend-run:
	npm --prefix gcmapview run dev

gcimport-install:
	uv sync --project gcimport

gcimport-test:
	uv run --project gcimport pytest

gcimport-run:
	uv run --project gcimport uvicorn gcimport.app:app --port 8001
