"""Configuration for IANA data sources."""

import logging
from typing import Final

IANA_URLS: Final[dict[str, str]] = {
    "RDAP_BOOTSTRAP": "https://data.iana.org/rdap/dns.json",
    "TLD_LIST": "https://data.iana.org/TLD/tlds-alpha-by-domain.txt",
    "ROOT_ZONE_DB": "https://www.iana.org/domains/root/db",
}

SOURCE_DIR: Final[str] = "data/source"

SOURCE_FILES: Final[dict[str, str]] = {
    "RDAP_BOOTSTRAP": "iana-rdap.json",
    "TLD_LIST": "iana-tlds.txt",
    "ROOT_ZONE_DB": "iana-root.html",
}


def setup_logging() -> None:
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
