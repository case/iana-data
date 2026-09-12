"""Parser and resolver for the editorial organizations seed.

Reads data/manual/organizations.json (identity only; the build adds roles) and
indexes it so a raw per-source org string resolves to one canonical record.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ..config import MANUAL_DIR, MANUAL_FILES
from ..utilities.file_io import read_json_file

logger = logging.getLogger(__name__)

OrgRecord = dict[str, Any]

# The provenance buckets shared by source_names, archived and roles.
SOURCES: tuple[str, ...] = ("iana", "icann", "asn")

# The complete key set of one archived entry. Unknown keys are a curation error.
ARCHIVED_ENTRY_KEYS: frozenset[str] = frozenset({"name", "archived_on"})

# date.fromisoformat also accepts "20260912", which the seed must not carry.
_ARCHIVED_ON_SHAPE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_organizations_manual(filepath: Path | None = None) -> list[OrgRecord]:
    """Parse the editorial organizations file into a list of records.

    Args:
        filepath: Path to organizations.json (defaults to the configured location).

    Returns:
        The org records as authored (identity only; the build adds ``roles``).
        An empty list if the file is missing or not a JSON array.

    Side effects:
        Logs every ``validate_organizations`` problem at ERROR. Records are
        returned as authored either way; the integrity tests are what fail.
    """
    if filepath is None:
        filepath = Path(MANUAL_DIR) / MANUAL_FILES["ORGANIZATIONS"]

    data = read_json_file(filepath, default=[])
    if not isinstance(data, list):
        logger.error("organizations.json is not a JSON array: %s", filepath)
        return []
    for problem in validate_organizations(data):
        logger.error("organizations.json: %s", problem)
    return data


def archived_names(org: OrgRecord, source: str) -> list[str]:
    """The archived names ``org`` carries for one bucket.

    Drops every entry whose shape ``validate_organizations`` rejects, so a
    malformed seed never resolves a key and never becomes drift evidence.
    """
    archived = org.get("archived")
    if not isinstance(archived, dict):
        return []
    entries = archived.get(source)
    if not isinstance(entries, list):
        return []
    return [
        entry["name"]
        for entry in entries
        if not _archived_entry_shape_problems("", entry)
    ]


def resolution_keys(org: OrgRecord) -> dict[str, list[str]]:
    """Every string that resolves to ``org``, per bucket.

    ``source_names`` and ``archived`` are bucket-scoped; ``display_name`` and
    ``aliases`` fall back into every bucket. This is the one definition of the
    resolver's key space, shared with the drift-tolerance helpers.
    """
    source_names = org.get("source_names", {})
    fallbacks = [org["display_name"], *org.get("aliases", [])]
    return {
        source: [
            *source_names.get(source, []),
            *archived_names(org, source),
            *fallbacks,
        ]
        for source in SOURCES
    }


def _string_set(value: Any) -> tuple[set[str], str]:
    """The strings in ``value``, and a problem description when it is not a list."""
    if not isinstance(value, list):
        return set(), f"is {type(value).__name__}, expected a list"
    return {item for item in value if isinstance(item, str)}, ""


def _validate_archived_on(where: str, value: Any) -> list[str]:
    """Problems with one ``archived_on`` value, or an empty list."""
    if not isinstance(value, str) or not _ARCHIVED_ON_SHAPE.match(value):
        return [f"{where} archived_on is {value!r}, expected YYYY-MM-DD"]
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        return [f"{where} archived_on {value!r} is not a real date: {exc}"]
    return []


def _archived_entry_shape_problems(where: str, entry: Any) -> list[str]:
    """Problems with one entry read alone; ``archived_names`` filters on this.

    Why a rejected shape also resolves nothing: docs/memory/log/2026-09-12-archived-bucket.md
    """
    if not isinstance(entry, dict):
        return [f"{where} entry is {type(entry).__name__}, expected an object"]

    problems = []
    if unknown := sorted(set(entry) - ARCHIVED_ENTRY_KEYS):
        problems.append(f"{where} entry has unknown key(s) {unknown}")
    if missing := sorted(ARCHIVED_ENTRY_KEYS - set(entry)):
        problems.append(f"{where} entry is missing {missing}")

    name = entry.get("name")
    if not isinstance(name, str) or not name:
        problems.append(f"{where} entry name is {name!r}, expected a non-empty string")
    if "archived_on" in entry:
        problems.extend(_validate_archived_on(where, entry.get("archived_on")))
    return problems


def _validate_archived_entry(
    where: str,
    entry: Any,
    seeded: set[str],
    aliases: set[str],
    seen: set[str],
) -> list[str]:
    """Problems with one archived entry in context; records its name in ``seen``."""
    problems = _archived_entry_shape_problems(where, entry)
    if not isinstance(entry, dict):
        return problems

    name = entry.get("name")
    if isinstance(name, str) and name:
        if name in seen:
            problems.append(f"{where} lists {name!r} twice")
        seen.add(name)
        if name in seeded:
            problems.append(f"{where} lists {name!r}, which is also a source_name")
        # An alias resolves in every bucket, so the archive entry would be inert.
        if name in aliases:
            problems.append(f"{where} lists {name!r}, which is also an alias")
    return problems


def validate_organizations(orgs: list[OrgRecord]) -> list[str]:
    """Report curation errors in the seed's ``archived`` buckets.

    Returns:
        One human-readable string per problem; empty when the seed is clean.
        Never raises, mirroring how ``build_resolver`` reports collisions: the
        integrity tests are what turn a problem into a failure.
    """
    problems: list[str] = []
    for index, org in enumerate(orgs):
        if not isinstance(org, dict):
            problems.append(
                f"orgs[{index}] is {type(org).__name__}, expected an object"
            )
            continue
        slug = org.get("slug", f"orgs[{index}]")
        archived = org.get("archived", {})
        if not isinstance(archived, dict):
            problems.append(
                f"{slug}: archived is {type(archived).__name__}, expected an object"
            )
            continue

        aliases, alias_problem = _string_set(org.get("aliases", []))
        if alias_problem:
            problems.append(f"{slug}: aliases {alias_problem}")
        source_names = org.get("source_names", {})
        if not isinstance(source_names, dict):
            problems.append(
                f"{slug}: source_names is {type(source_names).__name__}, "
                "expected an object"
            )
            source_names = {}

        for source, entries in archived.items():
            where = f"{slug}: archived.{source}"
            if source not in SOURCES:
                problems.append(f"{where} is not one of {list(SOURCES)}")
                continue
            if not isinstance(entries, list):
                problems.append(f"{where} is {type(entries).__name__}, expected a list")
                continue
            seeded, seed_problem = _string_set(source_names.get(source, []))
            if seed_problem:
                problems.append(f"{slug}: source_names.{source} {seed_problem}")
            seen: set[str] = set()
            for entry in entries:
                problems.extend(
                    _validate_archived_entry(where, entry, seeded, aliases, seen)
                )
    return problems


@dataclass(frozen=True)
class OrgResolver:
    """Resolves a raw per-source org string to one canonical record.

    Keys per bucket are its source_names and archived names plus
    display_name/aliases; collisions lists any string two orgs claim in one
    bucket (the integrity tests reject any).
    """

    by_source: dict[str, dict[str, OrgRecord]]
    collisions: list[tuple[str, str, str, str]]

    def resolve(self, source: str, name: str | None) -> OrgRecord | None:
        """Return the org a raw ``name`` resolves to in ``source``, or None."""
        if not name:
            return None
        return self.by_source.get(source, {}).get(name)


def build_resolver(orgs: list[OrgRecord]) -> OrgResolver:
    """Build an OrgResolver from manual org records.

    A key claimed by two different slugs within one bucket is recorded in
    ``collisions`` and the first claimant is kept (deterministic, never silently
    overwritten).
    """
    by_source: dict[str, dict[str, OrgRecord]] = {source: {} for source in SOURCES}
    collisions: list[tuple[str, str, str, str]] = []

    for org in orgs:
        slug = org["slug"]
        for source, names in resolution_keys(org).items():
            for name in names:
                existing = by_source[source].get(name)
                if existing is not None and existing["slug"] != slug:
                    collisions.append((source, name, existing["slug"], slug))
                    continue
                by_source[source][name] = org

    if collisions:
        logger.warning(
            "organizations.json: %d ambiguous source_name(s) across orgs: %s",
            len(collisions),
            collisions[:5],
        )
    return OrgResolver(by_source=by_source, collisions=collisions)
