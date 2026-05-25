#!/usr/bin/env python3
"""Download the ICANN gTLDs JSON Report.

Downloads the gTLDs report from ICANN and saves it to the source directory.
This file is updated daily and carries per-gTLD registry operator, contract,
and lifecycle metadata used to populate orgs.icann.* on each TLD record.
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

    key = "GTLDS_JSON"
    url = ICANN_URLS[key]
    filename = SOURCE_FILES[key]

    logger.info("Downloading gTLDs JSON report...")
    result = download_file(key=key, url=url, filename=filename)

    if result == "downloaded":
        print("gTLDs JSON report downloaded successfully")
        return 0
    elif result == "not_modified":
        print("gTLDs JSON report not modified")
        return 0
    else:
        print("Error downloading gTLDs JSON report")
        return 1


if __name__ == "__main__":
    sys.exit(main())
