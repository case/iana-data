"""Cache utilities for HTTP responses."""

import re
from datetime import datetime, timezone


def parse_cache_control_max_age(cache_control: str) -> int | None:
    """
    Parse max-age directive from Cache-Control header.

    Args:
        cache_control: Cache-Control header value

    Returns:
        Max-age value in seconds, or None if not found
    """
    match = re.search(r"max-age=(\d+)", cache_control)
    if match:
        return int(match.group(1))
    return None


def is_cache_fresh(metadata_entry: dict[str, str]) -> bool:
    """
    Check if cached file is still fresh based on Cache-Control.

    Args:
        metadata_entry: Metadata dict containing last_downloaded and headers.cache_max_age

    Returns:
        True if cache is still fresh, False otherwise
    """
    if "last_downloaded" not in metadata_entry:
        return False

    if "headers" not in metadata_entry or "cache_max_age" not in metadata_entry["headers"]:
        return False

    download_time = datetime.fromisoformat(metadata_entry["last_downloaded"])
    max_age = int(metadata_entry["headers"]["cache_max_age"])

    # Calculate age in seconds
    age = (datetime.now(timezone.utc) - download_time).total_seconds()

    return age < max_age
