#!/usr/bin/env python3
"""Rank tld_manager and orgs.tech values in data/generated/tlds.json.

For each operator name, print:
  - count of TLDs using it
  - whether it is already aliased (and to which canonical)
  - or, if it equals an existing canonical (the alias map's "self" form)

Use the output to spot candidates that should be folded into existing
canonicals, or new canonicals worth introducing.
"""

import json
from collections import Counter
from pathlib import Path

TLDS_PATH = Path("data/generated/tlds.json")
MANAGER_ALIASES_PATH = Path("data/manual/tld-manager-aliases.json")
TECH_ALIASES_PATH = Path("data/manual/tech-aliases.json")


def load_reverse_lookup(path: Path, top_key: str) -> dict[str, str]:
    """Build {raw_name: canonical} from an aliases file."""
    data = json.loads(path.read_text())
    return {
        entry["name"]: canon
        for canon, entries in data.get(top_key, {}).items()
        for entry in entries
    }


def load_canonicals(path: Path, top_key: str) -> set[str]:
    """Return the set of canonical names defined in an aliases file."""
    data = json.loads(path.read_text())
    return set(data.get(top_key, {}).keys())


def annotate(name: str, aliases: dict[str, str], canonicals: set[str]) -> str:
    """Return a short tag describing how `name` relates to the alias map."""
    if name in aliases:
        return f"aliased -> {aliases[name]}"
    if name in canonicals:
        return "canonical"
    return "unaliased"


def rank(counts: Counter[str], aliases: dict[str, str], canonicals: set[str]) -> None:
    """Print one line per operator, sorted by TLD count descending."""
    for name, count in counts.most_common():
        tag = annotate(name, aliases, canonicals)
        print(f"  {count:4d}  [{tag}]  {name}")


def main() -> None:
    tlds = json.loads(TLDS_PATH.read_text())["tlds"]
    manager_aliases = load_reverse_lookup(MANAGER_ALIASES_PATH, "managerAliases")
    manager_canonicals = load_canonicals(MANAGER_ALIASES_PATH, "managerAliases")
    tech_aliases = load_reverse_lookup(TECH_ALIASES_PATH, "techAliases")
    tech_canonicals = load_canonicals(TECH_ALIASES_PATH, "techAliases")

    managers: Counter[str] = Counter()
    techs: Counter[str] = Counter()
    for entry in tlds:
        iana_orgs = entry.get("orgs", {}).get("iana", {})
        manager = iana_orgs.get("sponsor")
        if manager and manager != "Not assigned":
            managers[manager] += 1
        tech = iana_orgs.get("tech")
        if tech:
            techs[tech] += 1

    print(
        f"=== tld_manager ({len(managers)} distinct, {sum(managers.values())} TLDs) ==="
    )
    rank(managers, manager_aliases, manager_canonicals)

    print()
    print(f"=== orgs.tech ({len(techs)} distinct, {sum(techs.values())} TLDs) ===")
    rank(techs, tech_aliases, tech_canonicals)


if __name__ == "__main__":
    main()
