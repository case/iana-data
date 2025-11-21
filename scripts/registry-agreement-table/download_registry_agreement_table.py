#!/usr/bin/env python3
"""Download ICANN Registry Agreement Table CSV.

Downloads the registry agreement table from ICANN and saves it to the source directory.
This file is updated monthly and contains agreement metadata for gTLDs.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import ICANN_URLS, SOURCE_FILES, setup_logging
from src.utilities.download import download_file

logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point."""
    setup_logging()

    key = "REGISTRY_AGREEMENT_TABLE"
    url = ICANN_URLS[key]
    filename = SOURCE_FILES[key]

    logger.info("Downloading registry agreement table...")
    result = download_file(key=key, url=url, filename=filename)

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
