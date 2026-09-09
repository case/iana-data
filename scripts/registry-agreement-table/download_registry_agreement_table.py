"""Download the ICANN Registry Agreement Table.

The table is rendered from the registry agreements page's embedded state rather
than ICANN's ``/csvdownload`` endpoint, which has returned HTTP 502 since at least
2026-07-30. See docs/memory/log/2026-09-07-registry-agreement-csv.md.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import ICANN_URLS, SOURCE_FILES, setup_logging
from src.parse.registry_agreement_page import render_registry_agreement_csv
from src.utilities.download import download_file

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point."""
    setup_logging()

    key = "REGISTRY_AGREEMENT_TABLE"
    url = ICANN_URLS[key]
    filename = SOURCE_FILES[key]

    logger.info("Downloading registry agreement table...")
    result = download_file(
        key=key, url=url, filename=filename, transform=render_registry_agreement_csv
    )

    if result == "downloaded":
        print("Registry agreement table downloaded successfully")
        return 0
    elif result == "not_modified":
        print("Registry agreement table not modified")
        return 0
    else:
        print("Error downloading registry agreement table")
        return 1


if __name__ == "__main__":
    sys.exit(main())
