"""Resolve a date-prefixed test fixture by its slug.

Fixtures are named ``yyyy-mm-dd-{slug}``, where the date is the capture date.
A changed upstream format gets a new dated file and the old one stays.
"""

import re
from datetime import date
from pathlib import Path

_DATE_PREFIX = re.compile(r"(\d{4}-\d{2}-\d{2})-(.+)")


def latest_fixture(directory: Path, slug: str) -> Path:
    """Return the fixture in ``directory`` with the latest date for ``slug``.

    Raises:
        FileNotFoundError: no file is named ``yyyy-mm-dd-{slug}`` exactly.
        ValueError: a matching file carries a date prefix that is not a real date.
    """
    dated: list[tuple[date, Path]] = []
    for path in directory.iterdir():
        match = _DATE_PREFIX.fullmatch(path.name)
        if match is None or match.group(2) != slug or not path.is_file():
            continue
        try:
            captured = date.fromisoformat(match.group(1))
        except ValueError as exc:
            raise ValueError(f"{path} has an impossible date prefix: {exc}") from exc
        dated.append((captured, path))

    if not dated:
        raise FileNotFoundError(f"no dated fixture for {slug!r} in {directory}")
    return max(dated)[1]
