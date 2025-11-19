.PHONY: deps
deps:
	uv sync

.PHONY: download-core
download-core:
	uv run python -m src.cli --download

.PHONY: download-tld-pages
download-tld-pages:
	uv run python -m src.cli --download-tld-pages $(GROUPS)

.PHONY: analyze
analyze:
	uv run python -m src.cli --analyze

.PHONY: build
build:
	uv run python -m src.cli --build

.PHONY: lint
lint:
	uv run ruff check src/ tests/

.PHONY: typecheck
typecheck:
	uv run pyright src/

.PHONY: test
test: lint typecheck
	uv run pytest

.PHONY: coverage
coverage: lint
	uv run pytest --cov=src --cov-report=term-missing
