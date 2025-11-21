"""Configuration for IANA data sources."""

import logging
from typing import Final

IANA_URLS: Final[dict[str, str]] = {
    "RDAP_BOOTSTRAP": "https://data.iana.org/rdap/dns.json",
    "TLD_LIST": "https://data.iana.org/TLD/tlds-alpha-by-domain.txt",
    "ROOT_ZONE_DB": "https://www.iana.org/domains/root/db",
}

SOURCE_DIR: Final[str] = "data/source"
TLD_PAGES_DIR: Final[str] = "data/source/tld-pages"

SOURCE_FILES: Final[dict[str, str]] = {
    "RDAP_BOOTSTRAP": "iana-rdap.json",
    "TLD_LIST": "iana-tlds.txt",
    "ROOT_ZONE_DB": "iana-root.html",
}

MANUAL_DIR: Final[str] = "data/manual"
GENERATED_DIR: Final[str] = "data/generated"
TLDS_OUTPUT_FILE: Final[str] = f"{GENERATED_DIR}/tlds.json"
IDN_SCRIPT_MAPPING_FILE: Final[str] = f"{GENERATED_DIR}/idn-script-mapping.json"

# Test fixtures
FIXTURES_DIR: Final[str] = "tests/fixtures"
FIXTURES_FILES: Final[dict[str, str]] = {
    "IDN_SCRIPT_MAPPING": "idn-script-mapping.json",
}

# ccTLD overrides for codes not in ISO 3166-1
CCTLD_OVERRIDES: Final[dict[str, str]] = {
    "ac": "Ascension Island",
    "eu": "European Union",
    "su": "Soviet Union",
    "uk": "United Kingdom",
}


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
