.PHONY: docker-up frontend-install frontend-build frontend-run

docker-up:
	docker compose -f geocomponents/docker-compose.yml up

frontend-install:
	npm --prefix gcmapview install --ignore-scripts

frontend-build:
	npm --prefix gcmapview run build

frontend-run:
	npm --prefix gcmapview run dev
