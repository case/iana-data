"""Referential-integrity tests for places.json: no orphan records, every
geographic_scope TLD lands in a matching place, every parent/sovereign FK resolves."""

ISO_DESIGNATIONS = {
    "dependent_territory",
    "exceptionally_reserved",
    "transitionally_reserved",
    "special_area",
}


def _places(typed_graph):
    return typed_graph.places["places"]


def _tld_to_place(typed_graph):
    mapping = {}
    for place in _places(typed_graph):
        for tld in place["tlds"]:
            mapping[tld] = place["slug"]
    return mapping


def test_every_place_has_at_least_one_tld(typed_graph):
    """No orphan place records (a place with no TLD has nothing to anchor it)."""
    orphans = [p["slug"] for p in _places(typed_graph) if not p["tlds"]]

    assert orphans == [], f"places with no TLDs: {orphans}"


def test_no_tld_claimed_by_two_places(typed_graph):
    """Each TLD belongs to exactly one place."""
    seen: dict[str, str] = {}
    dupes = []
    for place in _places(typed_graph):
        for tld in place["tlds"]:
            if tld in seen:
                dupes.append((tld, seen[tld], place["slug"]))
            seen[tld] = place["slug"]

    assert dupes == [], f"TLDs claimed by two places: {dupes}"


def test_place_tlds_are_ascii_delegated_keys_in_tlds_json(typed_graph):
    """Every TLD in a place is an A-label, a real tlds.json key, AND delegated."""
    bad = []
    for place in _places(typed_graph):
        for tld in place["tlds"]:
            entry = typed_graph.tlds.get(tld)
            if not tld.isascii():
                bad.append((place["slug"], tld, "non-ascii"))
            elif entry is None:
                bad.append((place["slug"], tld, "unknown-tld"))
            elif not entry.get("delegated"):
                bad.append((place["slug"], tld, "not-delegated"))

    assert bad == [], f"invalid place TLDs: {bad}"


def test_every_geographic_scope_tld_lands_in_a_matching_place(typed_graph):
    """Forward: a TLD tagged geographic_scope=X is in exactly one place of
    subtype X. Catches orphaned geographic TLDs and subtype drift."""
    tld_to_place = _tld_to_place(typed_graph)
    by_slug = {p["slug"]: p for p in _places(typed_graph)}

    problems = []
    for tld, entry in typed_graph.tlds.items():
        # Retired/non-delegated ccTLDs (an, tp, eh, ...) still carry a derived
        # country scope but are deliberately absent from places.json.
        if not entry.get("delegated"):
            continue
        scope = entry.get("annotations", {}).get("geographic_scope")
        if not scope:
            continue
        place_slug = tld_to_place.get(tld)
        if place_slug is None:
            problems.append((tld, scope, "in no place"))
        elif by_slug[place_slug]["subtype"] != scope:
            problems.append(
                (tld, scope, f"place {place_slug} is {by_slug[place_slug]['subtype']}")
            )

    assert problems == [], (
        f"geographic_scope TLDs not in a matching place: {problems[:15]}"
    )


def test_every_delegated_cctld_resolves_to_a_place(typed_graph):
    """Coverage: no delegated ccTLD (ASCII or IDN) is left without a place."""
    placed = {tld for p in _places(typed_graph) for tld in p["tlds"]}
    orphans = [
        tld
        for tld, entry in typed_graph.tlds.items()
        if entry.get("delegated")
        and entry.get("iana_tag") == "country-code"
        and tld not in placed
    ]

    assert orphans == [], f"delegated ccTLDs with no place: {orphans}"


def test_parent_fks_resolve(typed_graph):
    """Every non-null parent points to a real place slug."""
    slugs = {p["slug"] for p in _places(typed_graph)}
    dangling = [
        (p["slug"], p["parent"])
        for p in _places(typed_graph)
        if p.get("parent") is not None and p["parent"] not in slugs
    ]

    assert dangling == [], f"places whose parent is not a place slug: {dangling}"


def test_iso_designation_enum_and_dependent_has_parent(typed_graph):
    """iso_designation uses only ISO 3166-1 vocabulary; dependents name a sovereign."""
    bad_values = []
    dependents_without_parent = []
    for place in _places(typed_graph):
        designation = place.get("iso_designation")
        if designation is None:
            continue
        if designation not in ISO_DESIGNATIONS:
            bad_values.append((place["slug"], designation))
        if designation == "dependent_territory" and not place.get("parent"):
            dependents_without_parent.append(place["slug"])

    assert bad_values == [], f"unknown iso_designation values: {bad_values}"
    assert dependents_without_parent == [], (
        f"dependent territories with no sovereign parent: {dependents_without_parent}"
    )


def test_uk_folds_to_gb(typed_graph):
    """The UK is one place slugged gb (alpha-2), carrying both .gb and .uk."""
    slugs = {p["slug"] for p in _places(typed_graph)}
    assert "uk" not in slugs
    gb = next(p for p in _places(typed_graph) if p["slug"] == "gb")
    assert {"gb", "uk"} <= set(gb["tlds"])


def test_idn_cctld_folds_into_its_country(typed_graph):
    """An IDN ccTLD joins its country's record, not a record of its own."""
    ru = next(p for p in _places(typed_graph) if p["slug"] == "ru")
    assert "xn--p1ai" in ru["tlds"]
    assert not any(p["slug"] == "xn--p1ai" for p in _places(typed_graph))


def test_places_sorted_unique_with_envelope(typed_graph):
    """Places are sorted by slug, slugs are unique, and the envelope is present."""
    slugs = [p["slug"] for p in _places(typed_graph)]
    assert slugs == sorted(slugs)
    assert len(slugs) == len(set(slugs))
    assert typed_graph.places["description"]
    assert typed_graph.places["sources"]
