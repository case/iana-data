"""Download utilities for IANA data files."""

import logging
import time
from pathlib import Path
from typing import Callable

import httpx

from ..config import IANA_URLS, SOURCE_DIR, SOURCE_FILES
from .cache import is_cache_fresh, parse_cache_control_max_age
from .metadata import load_metadata, save_metadata, utc_timestamp
from .urls import get_tld_file_path, get_tld_page_url
from .retry import make_request_with_retry

logger = logging.getLogger(__name__)


# =============================================================================
# Public API
# =============================================================================


def download_file(
    key: str,
    url: str,
    filename: str,
    content_validator: Callable[[Path, str], bool] | None = None,
) -> str:
    """
    Download a single file using conditional requests.

    This is the main public API for downloading files. Handles all aspects:
    - HTTP client creation
    - Conditional requests (If-Modified-Since, ETag)
    - Cache freshness checks
    - Metadata loading and saving
    - Directory creation
    - File writing

    Args:
        key: Metadata key for tracking this download
        url: URL to download from
        filename: Filename to save in SOURCE_DIR
        content_validator: Optional callback to check if content actually changed.
            Takes (filepath, new_content_text) and returns True if content changed.
            If returns False, file is not saved and "not_modified" is returned.

    Returns:
        Status: "downloaded", "not_modified", or "error"
    """
    filepath = Path(SOURCE_DIR) / filename

    # Ensure source directory exists
    Path(SOURCE_DIR).mkdir(parents=True, exist_ok=True)

    metadata = load_metadata()

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        result = _download_file_impl(
            client=client,
            key=key,
            url=url,
            filepath=filepath,
            metadata=metadata,
            content_validator=content_validator,
        )

    # Save updated metadata
    save_metadata(metadata)

    return result


def download_iana_files() -> dict[str, str]:
    """
    Download all IANA data files using conditional requests.

    Uses a single HTTP client and metadata save for efficiency when
    downloading multiple files.

    Returns:
        A dict mapping source keys to their download status:
        - "downloaded": File was updated
        - "not_modified": File hasn't changed
        - "error": Download failed
    """
    # Lazy imports to avoid circular dependency
    from ..parse import (
        rdap_json_content_changed,
        root_db_html_content_changed,
        tlds_txt_content_changed,
    )

    metadata = load_metadata()
    results: dict[str, str] = {}

    # Ensure source directory exists
    Path(SOURCE_DIR).mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for key, url in IANA_URLS.items():
            filename = SOURCE_FILES[key]
            filepath = Path(SOURCE_DIR) / filename

            # Use content validators to ignore timestamp-only changes
            content_validator = None
            if key == "TLD_LIST":
                content_validator = tlds_txt_content_changed
            elif key == "RDAP_BOOTSTRAP":
                content_validator = rdap_json_content_changed
            elif key == "ROOT_ZONE_DB":
                content_validator = root_db_html_content_changed

            results[key] = _download_file_impl(
                client=client,
                key=key,
                url=url,
                filepath=filepath,
                metadata=metadata,
                content_validator=content_validator,
            )

    # Save updated metadata
    save_metadata(metadata)

    return results


def download_tld_pages(
    tlds: list[str] | None = None,
    base_dir: Path | None = None,
    delay: float = 1.0,
) -> dict[str, str]:
    """
    Download TLD detail pages from IANA.

    Args:
        tlds: List of TLDs to download. If None, downloads all TLDs from source file
        base_dir: Base directory for storing pages. Defaults to data/source/tld-pages
        delay: Seconds to wait between requests to avoid hammering server (default: 1.0)

    Returns:
        Dict mapping TLD to status: "downloaded", "error"
    """
    # Lazy imports to avoid circular dependency
    from ..parse import extract_main_content, parse_tlds_txt

    if base_dir is None:
        base_dir = Path("data/source/tld-pages")

    # Get TLD list if not provided
    if tlds is None:
        tlds = parse_tlds_txt()
        if not tlds:
            logger.error("No TLDs found. Run --download first to fetch the TLD list.")
            return {}

    # Load metadata
    metadata = load_metadata()

    results: dict[str, str] = {}

    # Update last_checked timestamp
    checked_time = utc_timestamp()

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for i, tld in enumerate(tlds):
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
                else:
                    logger.error("HTTP %d for %s", response.status_code, tld)
                    results[tld] = "error"

            except Exception as e:
                logger.error("Error downloading %s: %s", tld, e)
                results[tld] = "error"

            # Rate limiting: wait between requests (skip after last item)
            if delay > 0 and i < len(tlds) - 1:
                time.sleep(delay)

    # Update metadata with TLD_HTML entry
    metadata["TLD_HTML"] = {
        "last_checked": checked_time,
    }

    # Save metadata
    save_metadata(metadata)

    return results


# =============================================================================
# Internal Implementation
# =============================================================================


def _download_file_impl(
    client: httpx.Client,
    key: str,
    url: str,
    filepath: Path,
    metadata: dict,
    content_validator: Callable[[Path, str], bool] | None = None,
) -> str:
    """
    Internal implementation for downloading a single file.

    Used by both download_file() and download_iana_files() to share logic
    while allowing efficient batching with a single client/metadata.

    Args:
        client: httpx Client instance
        key: Metadata key for tracking this download
        url: URL to download from
        filepath: Local path to save file to
        metadata: Metadata dict (modified in place)
        content_validator: Optional callback to check if content actually changed.

    Returns:
        Status: "downloaded", "not_modified", or "error"
    """
    # Check if cache is still fresh (for Cache-Control based files)
    if key in metadata and is_cache_fresh(metadata[key]):
        logger.info("Cache still fresh for %s", key)
        # Update last_checked even for cache-fresh files
        if key not in metadata:
            metadata[key] = {}
        metadata[key]["last_checked"] = utc_timestamp()
        return "not_modified"

    # Prepare conditional request headers
    headers: dict[str, str] = {}
    if key in metadata and "cache_data" in metadata[key]:
        if "etag" in metadata[key]["cache_data"]:
            headers["If-None-Match"] = metadata[key]["cache_data"]["etag"]
        if "last_modified" in metadata[key]["cache_data"]:
            headers["If-Modified-Since"] = metadata[key]["cache_data"]["last_modified"]

    try:
        response = make_request_with_retry(client, url, headers=headers)

        # Initialize metadata entry if needed
        if key not in metadata:
            metadata[key] = {}

        # Always update last_checked timestamp
        metadata[key]["last_checked"] = utc_timestamp()

        if response.status_code == 304:
            # Not modified
            return "not_modified"
        elif response.status_code == 200:
            # Check with content validator if provided
            if content_validator and not content_validator(filepath, response.text):
                return "not_modified"

            # Download successful, save file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(response.content)

            # Initialize cache_data if needed
            if "cache_data" not in metadata[key]:
                metadata[key]["cache_data"] = {}

            # Update cache data with response headers
            if "etag" in response.headers:
                metadata[key]["cache_data"]["etag"] = response.headers["etag"]
            if "last-modified" in response.headers:
                metadata[key]["cache_data"]["last_modified"] = response.headers[
                    "last-modified"
                ]

            # Handle Cache-Control header
            if "cache-control" in response.headers:
                max_age = parse_cache_control_max_age(response.headers["cache-control"])
                if max_age:
                    metadata[key]["cache_data"]["cache_control"] = response.headers[
                        "cache-control"
                    ]
                    metadata[key]["cache_data"]["cache_max_age"] = str(max_age)
                    # For Cache-Control, also store download time for freshness calculation
                    metadata[key]["cache_data"]["last_downloaded"] = utc_timestamp()

            return "downloaded"
        else:
            return "error"
    except Exception as e:
        logger.error("Error downloading %s: %s", key, e)
        return "error"
