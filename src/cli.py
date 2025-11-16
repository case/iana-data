#!/usr/bin/env python3
"""Command-line interface for IANA data ETL."""

import argparse
import logging
import sys

from .config import IANA_URLS, setup_logging
from .utilities import download_iana_files

logger = logging.getLogger(__name__)


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="IANA data ETL command-line interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--download",
        nargs="*",
        metavar="SOURCE",
        help=(
            "Download IANA data files. "
            "Specify sources to download (e.g., RDAP_BOOTSTRAP TLD_LIST), "
            "or omit to download all files."
        ),
    )

    args = parser.parse_args()

    # Configure logging
    setup_logging()

    if args.download is not None:
        # Determine which files to download
        if len(args.download) == 0:
            # Download all files
            logger.info("Downloading all IANA data files...")
            sources_to_download = list(IANA_URLS.keys())
        else:
            # Download specific files
            sources_to_download = [s.upper() for s in args.download]

            # Validate source keys
            invalid_sources = [s for s in sources_to_download if s not in IANA_URLS]
            if invalid_sources:
                logger.error("Invalid source(s): %s", ", ".join(invalid_sources))
                logger.info("Valid sources: %s", ", ".join(IANA_URLS.keys()))
                return 1

            logger.info("Downloading: %s", ", ".join(sources_to_download))

        # Perform download
        results = download_iana_files()

        # Report results
        logger.info("Download results:")
        for source in sources_to_download:
            status = results.get(source, "unknown")
            status_symbol = {
                "downloaded": "✓",
                "not_modified": "-",
                "error": "✗",
            }.get(status, "?")

            log_func = logger.error if status == "error" else logger.info
            log_func("  %s %s: %s", status_symbol, source, status)

        # Return error code if any downloads failed
        if any(results.get(s) == "error" for s in sources_to_download):
            return 1

        return 0

    # No arguments provided
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
