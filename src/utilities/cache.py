"""Cache utilities for HTTP responses."""

import re
from datetime import datetime, timezone
from typing import Any


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


def is_cache_fresh(metadata_entry: dict[str, Any]) -> bool:
    """
    Check if cached file is still fresh based on Cache-Control.

    Args:
        metadata_entry: Metadata dict containing cache_data.last_downloaded and cache_data.cache_max_age

    Returns:
        True if cache is still fresh, False otherwise
    """
    if "cache_data" not in metadata_entry:
        return False

    cache_data = metadata_entry["cache_data"]

    if "last_downloaded" not in cache_data or "cache_max_age" not in cache_data:
        return False

    download_time = datetime.fromisoformat(cache_data["last_downloaded"])
    max_age = int(cache_data["cache_max_age"])

    # Calculate age in seconds
    age = (datetime.now(timezone.utc) - download_time).total_seconds()

    return age < max_age
