"""Command-line interface for IANA data ETL."""

import argparse
import logging
import sys
from pathlib import Path

from .analyze import analyze_rdap_json, analyze_tlds_txt
from .build import build_tlds_json
from .config import IANA_URLS, SOURCE_DIR, SOURCE_FILES, setup_logging
from .utilities import download_iana_files, download_iptoasn

logger = logging.getLogger(__name__)

# --download outcomes that keep every stored file usable.
EXIT_FETCH_FAILED = 3
EXIT_PAYLOAD_REJECTED = 4


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

    parser.add_argument(
        "--build",
        action="store_true",
        help="Build enhanced TLD data file (tlds.json)",
    )

    parser.add_argument(
        "--preserve-asn",
        action="store_true",
        help="Keep ASN values from the committed tlds.json instead of reading the "
        "local iptoasn file (avoids ASN churn on a local refresh).",
    )

    parser.add_argument(
        "--download-iptoasn",
        action="store_true",
        help="Download iptoasn data file for ASN lookups during build.",
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
                "invalid": "✗",
            }.get(status, "?")

            failed = status in {"error", "invalid"}
            log_func = logger.error if failed else logger.info
            log_func("  %s %s: %s", status_symbol, source, status)

        # Not 1 or 2: an uncaught exception exits 1 and argparse exits 2, and the
        # nightly continues on these two codes only.
        if any(results.get(s) == "invalid" for s in sources_to_download):
            return EXIT_PAYLOAD_REJECTED
        if any(results.get(s) == "error" for s in sources_to_download):
            return EXIT_FETCH_FAILED

        return 0

    if args.analyze is not None:
        # Define available analyzers
        analyzers = {
            "tlds-txt": lambda: analyze_tlds_txt(
                Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]
            ),
            "rdap": lambda: analyze_rdap_json(
                Path(SOURCE_DIR) / SOURCE_FILES["RDAP_BOOTSTRAP"]
            ),
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

    if args.build:
        logger.info("Building enhanced TLD data file...")
        result = build_tlds_json(preserve_asn=args.preserve_asn)

        if result.get("error"):
            logger.error("Build failed: %s", result["error"])
            return 1

        # Format file size for display
        file_size = result.get("file_size", 0)
        if file_size >= 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        elif file_size >= 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} bytes"

        logger.info("Build complete:")
        logger.info("  Total TLDs: %d", result["total_tlds"])
        logger.info("  Output file: %s", result.get("output_file"))
        logger.info("  File size: %s", size_str)

        # Show whether content changed
        if result.get("changed"):
            logger.info("  Status: Updated (content changed)")
        else:
            logger.info("  Status: Unchanged (content identical)")

        return 0

    if args.download_iptoasn:
        logger.info("Downloading iptoasn data...")
        result = download_iptoasn()

        if result == "downloaded":
            logger.info("  ✓ iptoasn: downloaded")
            return 0
        else:
            logger.error("  ✗ iptoasn: %s", result)
            return 1

    # No arguments provided
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
