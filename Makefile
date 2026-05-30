.PHONY: help
help:
	@echo "Available commands:"
	@echo "  make analyze                   Analyze downloaded data"
	@echo "  make analyze-idn-scripts       Analyze IDN scripts"
	@echo "  make analyze-registry-agreements  Analyze registry agreements"
	@echo "  make analyze-tlds-json         Analyze TLDs JSON"
	@echo "  make check-circular-imports    Check for circular imports with pydeps"
	@echo "  make checkly-deploy            Deploy Checkly checks (production)"
	@echo "  make checkly-info              Show Checkly info"
	@echo "  make checkly-preview-deploy    Deploy Checkly checks (preview)"
	@echo "  make checkly-test              Run Checkly tests"
	@echo "  make download-core             Download core IANA data files"
	@echo "  make download-iptoasn          Download iptoasn data for ASN lookups"
	@echo "  make download-tld-pages        Download TLD pages (optional GROUPS=...)"
	@echo "  make generate-idn-mapping      Generate IDN script mapping"
	@echo "  make typecheck                 Run pyright type checker"
	@echo ""
	@echo "Scripts (run directly, not via make):"
	@echo "  bin/setup                      Install dependencies (uv sync, pnpm install)"
	@echo "  bin/lint                       Run ruff check, ruff format check, pyright"
	@echo "  bin/test                       Run lint then pytest"
	@echo "  bin/build --preserve-asn       Build, keeping committed ASN (local/dev; no iptoasn refresh)"
	@echo "  bin/build --all                Full build, refreshing ASN from iptoasn (CI)"
	@echo "  bin/fetch-coordinates          Fetch geo-place lat/lon from Wikidata (--refresh to redo)"

.PHONY: download-core
download-core:
	uv run python -m src.cli --download

.PHONY: download-tld-pages
download-tld-pages:
	uv run python -m src.cli --download-tld-pages $(GROUPS)

.PHONY: download-iptoasn
download-iptoasn:
	uv run python -m src.cli --download-iptoasn

.PHONY: analyze
analyze:
	uv run python -m src.cli --analyze

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

.PHONY: typecheck
typecheck:
	uv run pyright src/

.PHONY: check-circular-imports
check-circular-imports:
	uv run pydeps src --no-output

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
