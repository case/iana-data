"""URL and path utilities for IANA data files."""

from pathlib import Path


def get_tld_page_url(tld: str) -> str:
    """
    Generate the IANA URL for a TLD detail page.

    Args:
        tld: The TLD (e.g., "com", "xn--2scrj9c")

    Returns:
        Full URL to the TLD's IANA detail page
    """
    return f"https://www.iana.org/domains/root/db/{tld}.html"


def get_tld_file_path(tld: str, base_dir: Path) -> Path:
    """
    Determine the file path for storing a TLD's HTML content.

    Args:
        tld: The TLD (e.g., "com", "xn--2scrj9c")
        base_dir: Base directory for storing TLD pages

    Returns:
        Path to the file where TLD HTML should be saved
    """
    if tld.startswith("xn--"):
        directory = "idn"
    else:
        directory = tld[0].lower()

    return base_dir / directory / f"{tld}.html"
