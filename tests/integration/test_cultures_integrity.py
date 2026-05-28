"""Referential-integrity tests for cultures.json: no orphan records,
cultural_affiliation round-trips, every TLD is a real ASCII tlds.json key."""


def _cultures(typed_graph):
    return typed_graph.cultures["cultures"]


def test_every_culture_has_at_least_one_tld(typed_graph):
    """No orphan culture records."""
    orphans = [c["slug"] for c in _cultures(typed_graph) if not c["tlds"]]

    assert orphans == [], f"cultures with no TLDs: {orphans}"


def test_cultural_affiliation_round_trips(typed_graph):
    """Every cultural_affiliation tag resolves to a culture that lists the TLD,
    and every TLD a culture lists carries that affiliation."""
    by_slug = {c["slug"]: c for c in _cultures(typed_graph)}

    # Forward: tag -> culture lists the TLD.
    forward = []
    for tld, entry in typed_graph.tlds.items():
        affiliation = entry.get("annotations", {}).get("cultural_affiliation")
        if affiliation and tld not in by_slug.get(affiliation, {"tlds": []})["tlds"]:
            forward.append((tld, affiliation))
    assert forward == [], (
        f"cultural_affiliation tags not reflected in cultures.json: {forward}"
    )

    # Backward: culture TLD -> the TLD carries that affiliation.
    backward = []
    for culture in _cultures(typed_graph):
        for tld in culture["tlds"]:
            tag = (
                typed_graph.tlds[tld].get("annotations", {}).get("cultural_affiliation")
            )
            if tag != culture["slug"]:
                backward.append((culture["slug"], tld, tag))
    assert backward == [], f"culture TLDs whose affiliation disagrees: {backward}"


def test_culture_tlds_are_ascii_keys_in_tlds_json(typed_graph):
    """Every TLD in a culture is an A-label (ASCII) and a real tlds.json key."""
    bad = []
    for culture in _cultures(typed_graph):
        for tld in culture["tlds"]:
            if not tld.isascii() or tld not in typed_graph.tlds:
                bad.append((culture["slug"], tld))

    assert bad == [], f"culture TLDs that are non-ASCII or not a tlds.json key: {bad}"


def test_cultures_sorted_with_envelope(typed_graph):
    """Cultures are sorted by slug, slugs unique, and the envelope is present."""
    slugs = [c["slug"] for c in _cultures(typed_graph)]
    assert slugs == sorted(slugs)
    assert len(slugs) == len(set(slugs))
    assert typed_graph.cultures["description"]
    assert typed_graph.cultures["sources"]
