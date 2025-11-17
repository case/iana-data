#!/usr/bin/env python3
"""Command-line interface for IANA data ETL."""

import argparse
import logging
import sys
from pathlib import Path

from .analyze import analyze_rdap_json, analyze_root_db_html, analyze_tlds_txt
from .config import IANA_URLS, SOURCE_DIR, SOURCE_FILES, setup_logging
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

    parser.add_argument(
        "--analyze",
        nargs="*",
        metavar="FILE",
        help=(
            "Analyze data files. "
            "Specify files to analyze (e.g., tlds-txt), "
            "or omit to analyze all files."
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

    if args.analyze is not None:
        # Define available analyzers
        analyzers = {
            "tlds-txt": lambda: analyze_tlds_txt(Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]),
            "root-db": lambda: analyze_root_db_html(Path(SOURCE_DIR) / SOURCE_FILES["ROOT_ZONE_DB"]),
            "rdap": lambda: analyze_rdap_json(Path(SOURCE_DIR) / SOURCE_FILES["RDAP_BOOTSTRAP"]),
        }

        # Determine which files to analyze
        if len(args.analyze) == 0:
            # Analyze all files
            logger.info("Analyzing all IANA data files...")
            files_to_analyze = list(analyzers.keys())
        else:
            # Analyze specific files
            files_to_analyze = args.analyze

            # Validate file names
            invalid_files = [f for f in files_to_analyze if f not in analyzers]
            if invalid_files:
                logger.error("Unknown file(s) to analyze: %s", ", ".join(invalid_files))
                logger.info("Available: %s", ", ".join(analyzers.keys()))
                return 1

        # Run analyzers
        results = []
        for i, file in enumerate(files_to_analyze):
            # Add blank line before each analyzer (except first)
            if i > 0:
                logger.info("")

            if file in analyzers:
                result = analyzers[file]()
                results.append(result)
            else:
                logger.info("Skipping %s (not implemented yet)", file)

        # Return error if any analysis failed
        if any(r != 0 for r in results):
            return 1

        return 0

    # No arguments provided
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
