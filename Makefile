.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make analyze                   Analyze downloaded data"
	@echo "  make analyze-idn-scripts       Analyze IDN scripts"
	@echo "  make analyze-registry-agreements  Analyze registry agreements"
	@echo "  make analyze-tlds-json         Analyze TLDs JSON"
	@echo "  make build                     Build output files (runs generate-idn-mapping first)"
	@echo "  make check-circular-imports    Check for circular imports with pydeps"
	@echo "  make checkly-deploy            Deploy Checkly checks (production)"
	@echo "  make checkly-info              Show Checkly info"
	@echo "  make checkly-preview-deploy    Deploy Checkly checks (preview)"
	@echo "  make checkly-test              Run Checkly tests"
	@echo "  make coverage                  Run tests with coverage report"
	@echo "  make deps                      Install dependencies (uv sync, npm install)"
	@echo "  make download-core             Download core IANA data files"
	@echo "  make download-tld-pages        Download TLD pages (optional GROUPS=...)"
	@echo "  make generate-idn-mapping      Generate IDN script mapping"
	@echo "  make lint                      Run ruff linter"
	@echo "  make test                      Run linter, typecheck, and tests"
	@echo "  make typecheck                 Run pyright type checker"

.PHONY: deps
deps:
	uv sync
	npm install

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
build: generate-idn-mapping
	uv run python -m src.cli --build

.PHONY: generate-idn-mapping
generate-idn-mapping:
	uv run python scripts/idn_unicode_scripts/generate_idn_script_mapping.py

.PHONY: analyze-idn-scripts
analyze-idn-scripts:
	uv run python scripts/idn_unicode_scripts/analyze_idn_scripts.py

.PHONY: analyze-registry-agreements
analyze-registry-agreements:
	uv run python scripts/registry-agreement-table/analyze_registry_agreements.py

.PHONY: analyze-tlds-json
analyze-tlds-json:
	uv run python scripts/analyze_tlds_json.py

.PHONY: lint
lint:
	uv run ruff check src/ tests/

.PHONY: typecheck
typecheck:
	uv run pyright src/

.PHONY: check-circular-imports
check-circular-imports:
	uv run pydeps src --no-output

.PHONY: test
test: lint typecheck
	uv run pytest

.PHONY: coverage
coverage: lint
	uv run pytest --cov=src --cov-report=term-missing

.PHONY: checkly-test
checkly-test:
	npx checkly test --config monitoring/checkly/checkly.config.ts

.PHONY: checkly-preview-deploy
checkly-preview-deploy:
	npx checkly deploy --preview --config monitoring/checkly/checkly.config.ts

.PHONY: checkly-deploy
checkly-deploy:
	npx checkly deploy --config monitoring/checkly/checkly.config.ts

.PHONY: checkly-info
checkly-info:
	npx jiti monitoring/checkly/info.ts
