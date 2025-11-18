.PHONY: deps
deps:
	uv sync

.PHONY: download
download:
	uv run python -m src.cli --download

.PHONY: analyze
analyze:
	uv run python -m src.cli --analyze

.PHONY: build
build:
	uv run python -m src.cli --build

.PHONY: lint
lint:
	uv run ruff check src/ tests/

.PHONY: test
test: lint
	uv run pytest

.PHONY: coverage
coverage: lint
	uv run pytest --cov=src --cov-report=term-missing
