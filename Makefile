.PHONY: docker-up frontend-install frontend-build frontend-run

docker-up:
	cd geocomponents && docker compose up

frontend-install:
	npm --prefix gcmapview install --ignore-scripts

frontend-build:
	npm --prefix gcmapview run build

frontend-run:
	npm --prefix gcmapview run dev
