.PHONY: deps
deps:
	uv sync

.PHONY: download
download:
	uv run python -m src.cli --download

.PHONY: test
test:
	uv run pytest
