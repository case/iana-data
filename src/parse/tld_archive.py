"""Loader for data/manual/tld-archive.json, the per-TLD archive seed.

Holds values no live source carries: ``tld_created``, and each ``iana_tag``
value IANA dropped. Unknown keys are errors and dates must be real.
"""

import json
import re
from pathlib import Path
from typing import Any

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.dates import iso_date_problem

TldArchive = dict[str, dict[str, Any]]

ENTRY_KEYS: frozenset[str] = frozenset({"tld_created", "archived"})
ARCHIVED_KEYS: frozenset[str] = frozenset({"iana_tag"})
ARCHIVED_VALUE_KEYS: frozenset[str] = frozenset({"value", "archived_on"})

# The iana_tag values IANA published until its 2026 Root Zone Database redesign.
ARCHIVED_IANA_TAGS: frozenset[str] = frozenset(
    {"sponsored", "generic-restricted", "infrastructure"}
)

_TLD_KEY = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")


class TldArchiveError(ValueError):
    """The TLD archive seed is unreadable or fails validation."""


def _archived_iana_tag_problems(where: str, value: Any) -> list[str]:
    if not isinstance(value, dict):
        return [f"{where} is {type(value).__name__}, expected an object"]
    problems = []
    if unknown := sorted(set(value) - ARCHIVED_VALUE_KEYS):
        problems.append(f"{where} has unknown key(s) {unknown}")
    if missing := sorted(ARCHIVED_VALUE_KEYS - set(value)):
        problems.append(f"{where} is missing {missing}")
    tag = value.get("value")
    # A list or object is unhashable, so the type is checked before membership.
    if "value" in value and not (isinstance(tag, str) and tag in ARCHIVED_IANA_TAGS):
        problems.append(
            f"{where} value is {tag!r}, expected one of {sorted(ARCHIVED_IANA_TAGS)}"
        )
    if "archived_on" in value and (problem := iso_date_problem(value["archived_on"])):
        problems.append(f"{where} archived_on {problem}")
    return problems


def _entry_problems(tld: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{tld} is {type(entry).__name__}, expected an object"]
    if not entry:
        return [f"{tld} is empty"]
    problems = []
    if unknown := sorted(set(entry) - ENTRY_KEYS):
        problems.append(f"{tld} has unknown key(s) {unknown}")
    if "tld_created" in entry and (problem := iso_date_problem(entry["tld_created"])):
        problems.append(f"{tld}: tld_created {problem}")
    if "archived" in entry:
        archived = entry["archived"]
        where = f"{tld}: archived"
        if not isinstance(archived, dict):
            problems.append(f"{where} is {type(archived).__name__}, expected an object")
        elif not archived:
            problems.append(f"{where} is empty")
        else:
            if unknown := sorted(set(archived) - ARCHIVED_KEYS):
                problems.append(f"{where} has unknown key(s) {unknown}")
            if "iana_tag" in archived:
                problems.extend(
                    _archived_iana_tag_problems(
                        f"{where}.iana_tag", archived["iana_tag"]
                    )
                )
    return problems


def validate_tld_archive(data: Any) -> list[str]:
    """Report every curation error in the seed; empty when it is clean."""
    if not isinstance(data, dict):
        return [f"seed is {type(data).__name__}, expected an object"]
    problems: list[str] = []
    for tld, entry in data.items():
        if not _TLD_KEY.fullmatch(tld):
            problems.append(f"{tld!r} is not a lowercase TLD label")
        problems.extend(_entry_problems(tld, entry))
    return problems


def parse_tld_archive(filepath: Path | None = None) -> TldArchive:
    """Read and validate the TLD archive seed.

    Args:
        filepath: Path to the seed (defaults to the configured location).

    Returns:
        Map of TLD to its archive entry, as authored.

    Raises:
        TldArchiveError: the file is missing, unreadable, not JSON, or has any
            ``validate_tld_archive`` problem.
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["TLD_ARCHIVE"]
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TldArchiveError(f"cannot read {filepath}: {exc}") from exc
    if problems := validate_tld_archive(data):
        raise TldArchiveError(f"{filepath}: " + "; ".join(problems))
    return data
