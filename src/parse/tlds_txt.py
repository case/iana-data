"""Parser for IANA TLDs text file."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_tlds_file(content: str) -> list[str]:
    """
    Parse a TLDs file, filtering out comments and empty lines.

    Args:
        content: The content of the TLDs file as a string

    Returns:
        List of TLDs (stripped, in original case)
    """
    lines = content.strip().split("\n")

    # Filter out comment lines (start with #) and empty lines
    tlds = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]

    return tlds


def tlds_txt_content_changed(filepath: Path, new_content: str) -> bool:
    """
    Check if TLD list content has actually changed.

    Ignores timestamp changes in comments - only compares actual TLD list.

    Args:
        filepath: Path to existing TLD file
        new_content: New content to compare against

    Returns:
        True if content changed, False if only timestamp changed
    """
    if not filepath.exists():
        return True

    # Parse new content
    new_tlds = parse_tlds_file(new_content)

    # Parse existing content
    existing_content = filepath.read_text()
    existing_tlds = parse_tlds_file(existing_content)

    # Only consider changed if actual TLD list differs
    if new_tlds == existing_tlds:
        logger.info("TLD content unchanged (only timestamp updated)")
        return False

    return True
