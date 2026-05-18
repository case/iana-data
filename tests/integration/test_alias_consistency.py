"""Cross-file consistency invariants for manual alias data.

These tests guard the canonical-name namespace shared by
data/manual/tld-manager-aliases.json and data/manual/tech-aliases.json.
"""

from src.parse.tech_aliases import parse_tech_aliases
from src.parse.tld_manager_aliases import parse_tld_manager_aliases


def test_overlapping_raw_names_map_to_same_canonical():
    """Any raw name in both alias files must map to the same canonical.

    Without this invariant the two annotations (tld_manager_alias and
    tech_alias) can disagree on the same entity, defeating the dedup
    that the manual files are supposed to provide.
    """
    manager = parse_tld_manager_aliases()
    tech = parse_tech_aliases()

    conflicts = {
        name: (manager[name], tech[name])
        for name in set(manager) & set(tech)
        if manager[name] != tech[name]
    }

    assert not conflicts, (
        f"Raw names mapping to different canonicals across alias files: {conflicts}"
    )
