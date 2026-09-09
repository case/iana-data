"""Download utilities for IANA data files."""

import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from ..config import (
    IANA_URLS,
    IPTOASN_DIR,
    IPTOASN_FILE,
    IPTOASN_URL,
    SOURCE_DIR,
    SOURCE_FILES,
)
from .cache import is_cache_fresh, parse_cache_control_max_age
from .metadata import load_metadata, save_metadata, utc_timestamp
from .retry import make_request_with_retry
from .urls import get_tld_file_path, get_tld_page_url

logger = logging.getLogger(__name__)


# =============================================================================
# Public API
# =============================================================================


def download_file(
    key: str,
    url: str,
    filename: str,
    content_validator: Callable[[Path, str], bool] | None = None,
    transform: Callable[[str], bytes] | None = None,
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
        transform: Optional callback converting the response body, decoded as
            UTF-8, into the bytes to save. For sources whose published file is
            derived from the fetched document. Raising from it makes the
            download fail rather than saving a partial file. When the result
            matches the file on disk, "not_modified" is returned.

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
            transform=transform,
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
    from ..parse import extract_main_content, parse_root_db_tlds

    if base_dir is None:
        base_dir = Path("data/source/tld-pages")

    # Get TLD list if not provided. Source from the root DB (all TLDs the build
    # iterates), not the delegated-only tlds.txt, so page coverage matches.
    if tlds is None:
        tlds = parse_root_db_tlds()
        if not tlds:
            logger.error(
                "No TLDs found. Run --download first to fetch the root zone database."
            )
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


def download_iptoasn() -> str:
    """
    Download the iptoasn combined TSV file.

    Downloads the gzipped file from iptoasn.com and saves it locally.
    This file is gitignored and used during build for ASN lookups.

    Returns:
        Status: "downloaded" or "error"
    """
    iptoasn_dir = Path(IPTOASN_DIR)
    iptoasn_dir.mkdir(parents=True, exist_ok=True)
    filepath = iptoasn_dir / IPTOASN_FILE

    try:
        logger.info("Downloading iptoasn data from %s...", IPTOASN_URL)
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = make_request_with_retry(client, IPTOASN_URL)

            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                size_mb = len(response.content) / (1024 * 1024)
                logger.info("  → %s (%.1f MB)", filepath, size_mb)
                metadata = load_metadata()
                metadata["IPTOASN"] = {"last_downloaded": utc_timestamp()}
                save_metadata(metadata)
                return "downloaded"
            else:
                logger.error("HTTP %d for %s", response.status_code, IPTOASN_URL)
                return "error"
    except Exception as e:
        logger.error("Error downloading iptoasn: %s", e)
        return "error"


def get_iptoasn_path() -> Path:
    """
    Get the path to the iptoasn data file.

    Returns:
        Path to ip2asn-combined.tsv.gz
    """
    return Path(IPTOASN_DIR) / IPTOASN_FILE


# =============================================================================
# Internal Implementation
# =============================================================================


def _drop_cache_from_other_url(key: str, url: str, metadata: dict) -> None:
    """Discard cache validators recorded against a different URL, or against none."""
    entry = metadata.get(key)
    if not entry or "cache_data" not in entry:
        return
    if entry["cache_data"].get("url") == url:
        return
    logger.info("Dropping cache data for %s: recorded against a different URL", key)
    del entry["cache_data"]


def _record_cache_data(
    key: str, url: str, response: httpx.Response, metadata: dict, *, saved: bool
) -> None:
    """Store the response's validators; `saved` restarts the freshness window."""
    cache_data = metadata[key].setdefault("cache_data", {})
    cache_data["url"] = url

    if "etag" in response.headers:
        cache_data["etag"] = response.headers["etag"]
    if "last-modified" in response.headers:
        cache_data["last_modified"] = response.headers["last-modified"]

    if "cache-control" in response.headers:
        max_age = parse_cache_control_max_age(response.headers["cache-control"])
        if max_age:
            cache_data["cache_control"] = response.headers["cache-control"]
            cache_data["cache_max_age"] = str(max_age)
            if saved:
                # is_cache_fresh measures staleness from this timestamp.
                cache_data["last_downloaded"] = utc_timestamp()


def _download_file_impl(
    client: httpx.Client,
    key: str,
    url: str,
    filepath: Path,
    metadata: dict,
    content_validator: Callable[[Path, str], bool] | None = None,
    transform: Callable[[str], bytes] | None = None,
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
        transform: Optional callback converting the response body into the bytes
            to save. See download_file.

    Returns:
        Status: "downloaded", "not_modified", or "error"
    """
    # Validators describe one URL. Repointing a key must not carry them across.
    _drop_cache_from_other_url(key, url, metadata)

    # Skipped for a transform: it never runs on this path, so an origin max-age
    # would freeze the derived file. Why: docs/memory/log/2026-09-07-registry-agreement-csv.md
    if transform is None and key in metadata and is_cache_fresh(metadata[key]):
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
                # Recorded here too: a source that reports "unchanged" every
                # night would otherwise never send a validator again.
                _record_cache_data(key, url, response, metadata, saved=False)
                return "not_modified"

            if transform is None:
                content = response.content
            else:
                # Decoded explicitly: httpx infers a charset from the header and
                # would silently mangle a transform that must be byte-exact.
                content = transform(response.content.decode("utf-8"))

            # A derived file often outlives changes elsewhere in its source document.
            derived_unchanged = (
                transform is not None
                and filepath.exists()
                and filepath.read_bytes() == content
            )

            if not derived_unchanged:
                # Download successful, save file
                filepath.parent.mkdir(parents=True, exist_ok=True)
                with open(filepath, "wb") as f:
                    f.write(content)

            # Only a response we processed to the end earns its validators. A
            # transform that raised must be retried, not answered with a 304.
            _record_cache_data(
                key, url, response, metadata, saved=not derived_unchanged
            )

            return "not_modified" if derived_unchanged else "downloaded"
        else:
            return "error"
    except Exception as e:
        logger.error("Error downloading %s: %s", key, e)
        return "error"
