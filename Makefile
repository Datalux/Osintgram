SHELL := /bin/bash

.PHONY: run test docker docker-build

run:
	@echo -e "\e[34m######## Osintgram Web UI — http://127.0.0.1:8000 (localhost only, no auth) ########\e[0m"
	@uvicorn src.web.app:app --host 127.0.0.1 --port 8000 --reload

test:
	@python -m pytest

docker-build:
	@docker compose build

docker:
	@echo -e "\e[34m######## Osintgram Web UI in Docker — http://127.0.0.1:8000 ########\e[0m"
	@docker compose up --build
