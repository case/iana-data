"""Download utilities for IANA data files."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import IANA_URLS, SOURCE_DIR, SOURCE_FILES
from ..parse import tlds_txt_content_changed
from .cache import is_cache_fresh, parse_cache_control_max_age
from .metadata import load_metadata, save_metadata

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
                response = client.get(url, headers=headers)

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
