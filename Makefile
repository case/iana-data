.PHONY: deps
deps:
	uv sync

.PHONY: download
download:
	uv run python -m src.cli --download

.PHONY: analyze
analyze:
	uv run python -m src.cli --analyze

.PHONY: test
test:
	uv run pytest
