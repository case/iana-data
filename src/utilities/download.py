"""Download utilities for IANA data files."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import IANA_URLS, SOURCE_DIR, SOURCE_FILES, TLDS_OUTPUT_FILE
from ..parse import extract_main_content, tlds_txt_content_changed
from .cache import is_cache_fresh, parse_cache_control_max_age
from .metadata import load_metadata, save_metadata
from .urls import get_tld_file_path, get_tld_page_url
from .retry import make_request_with_retry

logger = logging.getLogger(__name__)


def download_iana_files() -> dict[str, str]:
    """
    Download IANA data files using conditional requests.

    Uses If-Modified-Since and If-None-Match headers to avoid
    downloading files that haven't changed since the last fetch.

    Returns:
        A dict mapping source keys to their download status:
        - "downloaded": File was updated
        - "not_modified": File hasn't changed
        - "error": Download failed
    """
    metadata = load_metadata()
    results: dict[str, str] = {}

    # Ensure source directory exists
    Path(SOURCE_DIR).mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for key, url in IANA_URLS.items():
            filename = SOURCE_FILES[key]
            filepath = Path(SOURCE_DIR) / filename

            # Check if cache is still fresh (for Cache-Control based files)
            if key in metadata and is_cache_fresh(metadata[key]):
                results[key] = "not_modified"
                logger.info("Cache still fresh for %s", key)
                # Update last_checked even for cache-fresh files
                if key not in metadata:
                    metadata[key] = {}
                metadata[key]["last_checked"] = datetime.now(timezone.utc).isoformat()
                continue

            # Prepare conditional request headers
            headers: dict[str, str] = {}
            if key in metadata and "headers" in metadata[key]:
                if "etag" in metadata[key]["headers"]:
                    headers["If-None-Match"] = metadata[key]["headers"]["etag"]
                if "last_modified" in metadata[key]["headers"]:
                    headers["If-Modified-Since"] = metadata[key]["headers"]["last_modified"]

            try:
                response = make_request_with_retry(client, url, headers=headers)

                # Initialize metadata entry if needed
                if key not in metadata:
                    metadata[key] = {}
                if "headers" not in metadata[key]:
                    metadata[key]["headers"] = {}

                # Always update last_checked timestamp
                metadata[key]["last_checked"] = datetime.now(timezone.utc).isoformat()

                if response.status_code == 304:
                    # Not modified
                    results[key] = "not_modified"
                elif response.status_code == 200:
                    # Special handling for TLD_LIST - check if content actually changed
                    if key == "TLD_LIST" and not tlds_txt_content_changed(filepath, response.text):
                        results[key] = "not_modified"
                        continue

                    # Download successful, save file
                    with open(filepath, "wb") as f:
                        f.write(response.content)

                    # Update metadata with response headers
                    if "etag" in response.headers:
                        metadata[key]["headers"]["etag"] = response.headers["etag"]
                    if "last-modified" in response.headers:
                        metadata[key]["headers"]["last_modified"] = response.headers["last-modified"]

                    # Handle Cache-Control header
                    if "cache-control" in response.headers:
                        max_age = parse_cache_control_max_age(response.headers["cache-control"])
                        if max_age:
                            metadata[key]["headers"]["cache_control"] = response.headers["cache-control"]
                            metadata[key]["headers"]["cache_max_age"] = str(max_age)

                    # Update last_downloaded timestamp
                    metadata[key]["last_downloaded"] = datetime.now(timezone.utc).isoformat()

                    results[key] = "downloaded"
                else:
                    results[key] = "error"
            except Exception as e:
                logger.error("Error downloading %s: %s", key, e)
                results[key] = "error"

    # Save updated metadata
    save_metadata(metadata)

    return results


def download_tld_pages(
    tlds: list[str] | None = None,
    base_dir: Path | None = None,
) -> dict[str, str]:
    """
    Download TLD detail pages from IANA.

    Args:
        tlds: List of TLDs to download. If None, downloads all TLDs from tlds.json
        base_dir: Base directory for storing pages. Defaults to data/source/tld-pages

    Returns:
        Dict mapping TLD to status: "downloaded", "error"
    """
    if base_dir is None:
        base_dir = Path("data/source/tld-pages")

    # Get TLD list if not provided
    if tlds is None:
        tlds_json_path = Path(TLDS_OUTPUT_FILE)
        if tlds_json_path.exists():
            try:
                with open(tlds_json_path) as f:
                    data = json.load(f)
                tlds = [entry["tld"] for entry in data["tlds"]]
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.error("Error reading tlds.json: %s", e)
                return {}
        else:
            logger.error("tlds.json not found at %s. Run build first.", TLDS_OUTPUT_FILE)
            return {}

    # Load metadata
    metadata = load_metadata()

    # Track download statistics
    successful_downloads = 0
    failed_downloads = 0
    results: dict[str, str] = {}

    # Update last_checked timestamp
    checked_time = datetime.now(timezone.utc).isoformat()

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for tld in tlds:
            url = get_tld_page_url(tld)
            file_path = get_tld_file_path(tld, base_dir)

            try:
                logger.info("Downloading %s...", tld)
                response = make_request_with_retry(client, url)

                if response.status_code == 200:
                    # Extract main content
                    main_content = extract_main_content(response.text)

                    # Create directory if needed
                    file_path.parent.mkdir(parents=True, exist_ok=True)

                    if main_content:
                        # Save extracted main content
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(main_content)
                        logger.info("  → %s", file_path)
                    else:
                        # Fallback: save full HTML if main content extraction fails
                        fallback_path = file_path.with_stem(f"{file_path.stem}-full")
                        logger.warning(
                            "No <main> content found for %s, saving full HTML as fallback to %s",
                            tld,
                            fallback_path,
                        )
                        with open(fallback_path, "w", encoding="utf-8") as f:
                            f.write(response.text)
                        logger.info("  → %s (fallback)", fallback_path)

                    results[tld] = "downloaded"
                    successful_downloads += 1
                else:
                    logger.error("HTTP %d for %s", response.status_code, tld)
                    results[tld] = "error"
                    failed_downloads += 1

            except Exception as e:
                logger.error("Error downloading %s: %s", tld, e)
                results[tld] = "error"
                failed_downloads += 1

    # Update metadata with TLD_HTML entry
    metadata["TLD_HTML"] = {
        "last_checked": checked_time,
        "last_downloaded": datetime.now(timezone.utc).isoformat(),
        "total_tlds": len(tlds),
        "successful_downloads": successful_downloads,
        "failed_downloads": failed_downloads,
    }

    # Save metadata
    save_metadata(metadata)

    return results
