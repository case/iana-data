"""Referential-integrity tests for agreements.json: enum matches the canonical
ICANN mapping, registry_agreement_types round-trips, every record carries display + source."""

from src.config import REGISTRY_AGREEMENT_TYPE_MAPPING

CANONICAL_SLUGS = set(REGISTRY_AGREEMENT_TYPE_MAPPING.values())


def _agreements(typed_graph):
    return typed_graph.agreements["agreements"]


def test_enum_completeness(typed_graph):
    """The artifact's slugs are exactly the canonical ICANN agreement types.

    Tripwire (N3): if ICANN adds an agreement type, this fails until both the
    mapping and display names are updated."""
    slugs = {a["slug"] for a in _agreements(typed_graph)}
    assert slugs == CANONICAL_SLUGS, (
        f"agreements.json slugs {slugs} != canonical {CANONICAL_SLUGS}"
    )
    # And no TLD carries a type outside the canonical set.
    observed = {
        slug
        for entry in typed_graph.tlds.values()
        for slug in entry.get("annotations", {}).get("registry_agreement_types", [])
    }
    assert observed <= CANONICAL_SLUGS, (
        f"TLDs carry non-canonical types: {observed - CANONICAL_SLUGS}"
    )


def test_round_trips_with_tld_annotations(typed_graph):
    """registry_agreement_types on a TLD <-> the agreement's tlds[] list."""
    by_slug = {a["slug"]: a for a in _agreements(typed_graph)}

    forward = []
    for tld, entry in typed_graph.tlds.items():
        for slug in entry.get("annotations", {}).get("registry_agreement_types", []):
            if tld not in by_slug[slug]["tlds"]:
                forward.append((tld, slug))
    assert forward == [], (
        f"TLD agreement types missing from the reverse index: {forward[:15]}"
    )

    backward = []
    for agreement in _agreements(typed_graph):
        for tld in agreement["tlds"]:
            types = (
                typed_graph.tlds[tld]
                .get("annotations", {})
                .get("registry_agreement_types", [])
            )
            if agreement["slug"] not in types:
                backward.append((agreement["slug"], tld))
    assert backward == [], f"reverse-index TLDs that don't point back: {backward[:15]}"


def test_agreement_tlds_are_ascii_keys_in_tlds_json(typed_graph):
    """Every TLD in an agreement is an A-label (ASCII) and a real tlds.json key."""
    bad = []
    for agreement in _agreements(typed_graph):
        for tld in agreement["tlds"]:
            if not tld.isascii() or tld not in typed_graph.tlds:
                bad.append((agreement["slug"], tld))

    assert bad == [], f"agreement TLDs that are non-ASCII or not a tlds.json key: {bad}"


def test_every_agreement_has_display_name_and_source(typed_graph):
    """Each record carries a friendly display_name and the verbatim ICANN string."""
    inverse = {slug: raw for raw, slug in REGISTRY_AGREEMENT_TYPE_MAPPING.items()}
    problems = []
    for agreement in _agreements(typed_graph):
        if not agreement.get("display_name"):
            problems.append((agreement["slug"], "no display_name"))
        if agreement.get("source_names", {}).get("icann") != inverse[agreement["slug"]]:
            problems.append((agreement["slug"], "source_names.icann mismatch"))

    assert problems == [], f"agreement records missing display/source data: {problems}"


def test_agreements_sorted_with_envelope(typed_graph):
    """Agreements are sorted by slug and the envelope is present."""
    slugs = [a["slug"] for a in _agreements(typed_graph)]
    assert slugs == sorted(slugs)
    assert typed_graph.agreements["description"]
    assert typed_graph.agreements["sources"]


# Pinned set of delegated gTLDs where IANA-CSV brand and ICANN specification_13
# disagree. Rationale in README "Interpreting the data".
KNOWN_BRAND_STATUS_MISMATCHES: frozenset[str] = frozenset(
    {"baidu", "case", "diy", "food", "gmo", "monster", "nexus", "sbs"}
)


def test_known_brand_status_mismatches_are_pinned(typed_graph):
    """Delegated gTLDs where CSV-brand and specification_13 disagree are pinned."""
    mismatches = set()
    for tld, entry in typed_graph.tlds.items():
        if not entry.get("delegated") or entry.get("type") != "gtld":
            continue
        csv_brand = "brand" in entry.get("annotations", {}).get(
            "registry_agreement_types", []
        )
        spec13 = entry.get("orgs", {}).get("icann", {}).get("specification_13")
        if (csv_brand and spec13 is False) or (not csv_brand and spec13 is True):
            mismatches.add(tld)

    new = mismatches - KNOWN_BRAND_STATUS_MISMATCHES
    resolved = KNOWN_BRAND_STATUS_MISMATCHES - mismatches
    assert not new and not resolved, (
        f"Brand-status mismatch set changed. "
        f"New mismatches (review and add to KNOWN_BRAND_STATUS_MISMATCHES): "
        f"{sorted(new)}. Resolved mismatches (remove from set): {sorted(resolved)}."
    )
