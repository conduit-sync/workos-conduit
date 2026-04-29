.PHONY: install dev test lint fmt fmt-check clean docker-build docker-run

PYTHON ?= python3.13
VENV   ?= .venv

install:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e ".[dev]"

# Run with auto-reload, console logging, .env loaded
dev:
	LOG_FORMAT=console LOG_LEVEL=DEBUG \
	$(VENV)/bin/uvicorn src.main:app \
	  --host 0.0.0.0 --port 8080 --reload --reload-dir src

test:
	$(VENV)/bin/pytest

lint:
	$(VENV)/bin/ruff check src tests

fmt:
	$(VENV)/bin/black src tests
	$(VENV)/bin/ruff check --fix src tests

fmt-check:
	$(VENV)/bin/black --check src tests
	$(VENV)/bin/ruff check src tests

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache coverage.xml test-results.xml __pycache__

docker-build:
	docker build -t workos-conduit:dev .

docker-run:
	docker-compose up --build
