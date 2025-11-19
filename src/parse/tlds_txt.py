"""Parser for IANA TLDs text file."""

import logging
from pathlib import Path

from ..config import SOURCE_DIR, SOURCE_FILES

logger = logging.getLogger(__name__)


def parse_tlds_txt(filepath: Path | None = None, normalize: bool = True) -> list[str]:
    """
    Parse the IANA TLDs text file.

    Args:
        filepath: Path to the TLDs text file (defaults to configured location)
        normalize: If True, lowercase all TLDs (default: True)

    Returns:
        List of TLDs (stripped, lowercased if normalize=True)
    """
    if filepath is None:
        filepath = Path(SOURCE_DIR) / SOURCE_FILES["TLD_LIST"]

    try:
        content = filepath.read_text()
    except OSError as e:
        logger.error("Error reading TLDs text file from %s: %s", filepath, e)
        return []

    tlds = _parse_tlds_content(content)

    if normalize:
        tlds = [tld.lower() for tld in tlds]

    return tlds


def _parse_tlds_content(content: str) -> list[str]:
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
    new_tlds = _parse_tlds_content(new_content)

    # Parse existing content
    try:
        existing_content = filepath.read_text()
    except OSError as e:
        logger.error("Error reading existing TLDs file from %s: %s", filepath, e)
        return True  # Treat as changed if we can't read existing file

    existing_tlds = _parse_tlds_content(existing_content)

    # Only consider changed if actual TLD list differs
    if new_tlds == existing_tlds:
        logger.info("TLD content unchanged (only timestamp updated)")
        return False

    return True
