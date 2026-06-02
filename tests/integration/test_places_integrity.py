"""Referential-integrity tests for places.json: no orphan records, every
geographic_scope TLD lands in a matching place, every parent/sovereign FK resolves."""

import pycountry

from src.parse.country import is_cctld
from src.parse.manual_annotations import parse_manual_annotations

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


def _explicitly_scoped_tlds():
    """TLDs carrying an explicit geographic_scope in annotations.json: the
    deliberate-curation marker. Excludes ccTLDs whose country scope the build
    derives mechanically (an/tp/eh/...), which are not listed in the file."""
    return {
        tld
        for tld, fields in parse_manual_annotations().items()
        if fields.get("geographic_scope")
    }


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


def test_place_tlds_are_ascii_known_keys_in_tlds_json(typed_graph):
    """Every TLD in a place is an A-label and a real tlds.json key. It must be
    delegated, unless it is a deliberately-curated geographic TLD (one carrying an
    explicit geographic_scope in annotations.json). That exemption lets retired
    place TLDs (e.g. budapest, doha) keep a record while still rejecting any other
    undelegated TLD that drifts into a place."""
    scoped = _explicitly_scoped_tlds()
    bad = []
    for place in _places(typed_graph):
        for tld in place["tlds"]:
            entry = typed_graph.tlds.get(tld)
            if not tld.isascii():
                bad.append((place["slug"], tld, "non-ascii"))
            elif entry is None:
                bad.append((place["slug"], tld, "unknown-tld"))
            elif not entry.get("delegated") and tld not in scoped:
                bad.append((place["slug"], tld, "undelegated-and-unannotated"))

    assert bad == [], f"invalid place TLDs: {bad}"


def test_every_geographic_scope_tld_lands_in_a_matching_place(typed_graph):
    """Forward: a TLD tagged geographic_scope=X is in exactly one place of
    subtype X. Catches orphaned geographic TLDs and subtype drift."""
    tld_to_place = _tld_to_place(typed_graph)
    by_slug = {p["slug"]: p for p in _places(typed_graph)}
    scoped = _explicitly_scoped_tlds()

    problems = []
    for tld, entry in typed_graph.tlds.items():
        scope = entry.get("annotations", {}).get("geographic_scope")
        if not scope:
            continue
        # Retired/non-delegated ccTLDs (an, tp, eh, ...) carry a derived country
        # scope and are deliberately absent from places.json: skip those. A TLD
        # whose scope is explicitly annotated must land in a place even when
        # undelegated (e.g. the retired city gTLDs budapest, doha).
        if not entry.get("delegated") and tld not in scoped:
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


def test_iso_reserved_and_special_records_pinned(typed_graph):
    """Lock in the editorial shape for ISO 3166-1 reserved / special-area ccTLDs.

    pycountry lists AQ as a regular country, so the place record carries
    iso_code='AQ'; AC and SU are not in pycountry and stay null. The
    iso_designation field captures the actual ISO 3166-1 status either way.
    """
    by_slug = {p["slug"]: p for p in _places(typed_graph)}
    expected = {
        "ac": {
            "iso_designation": "exceptionally_reserved",
            "parent": "sh",
            "iso_code": None,
        },
        "su": {
            "iso_designation": "transitionally_reserved",
            "parent": None,
            "iso_code": None,
        },
        "aq": {"iso_designation": "special_area", "parent": None, "iso_code": "AQ"},
    }
    actual = {}
    for slug in expected:
        place = by_slug.get(slug)
        assert place is not None, f"places.json missing reserved-code record {slug!r}"
        assert place["subtype"] == "country", (
            f"{slug!r}: subtype should be 'country'; got {place['subtype']!r}"
        )
        assert place["tlds"] == [slug], (
            f"{slug!r}: tlds should be [{slug!r}]; got {place['tlds']!r}"
        )
        actual[slug] = {
            k: place.get(k) for k in ("iso_designation", "parent", "iso_code")
        }
    assert actual == expected, (
        f"reserved-code shape drifted: expected {expected}, got {actual}"
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


def test_gtld_folds_into_its_country(typed_graph):
    """A culture/community gTLD with a fold_into_country annotation (swiss -> ch,
    kiwi -> nz) joins that country's record, not a record of its own (mirrors the
    IDN fold). Derived from annotations.json so new folds are covered without edits."""
    by_slug = {p["slug"]: p for p in _places(typed_graph)}
    folds = {
        tld: fields["fold_into_country"].lower()
        for tld, fields in parse_manual_annotations().items()
        if fields.get("fold_into_country")
    }
    assert folds, "expected at least one fold_into_country entry (swiss, kiwi)"
    for gtld, country in folds.items():
        assert gtld in by_slug[country]["tlds"], f"{gtld} not folded into {country}"
        assert not any(p["slug"] == gtld for p in _places(typed_graph)), (
            f"{gtld} should not also have a standalone place"
        )


def test_fold_into_country_consistent_and_resolves():
    """fold_into_country and geographic_scope stay in sync, and the target is a
    real ISO country. Guards both desync directions between annotations.json and
    the src/build/places.py fold: a fold without country scope, a country-scoped
    gTLD with no fold target, and a fold naming a non-country."""
    problems = []
    for tld, fields in parse_manual_annotations().items():
        fold = fields.get("fold_into_country")
        scope = fields.get("geographic_scope")
        if fold:
            if scope != "country":
                problems.append((tld, f"fold_into_country but scope={scope!r}"))
            if pycountry.countries.get(alpha_2=fold.upper()) is None:
                problems.append((tld, f"fold target {fold!r} is not an ISO country"))
        if scope == "country" and not is_cctld(tld) and not fold:
            problems.append((tld, "country-scoped gTLD without fold_into_country"))
    assert problems == [], f"fold_into_country inconsistencies: {problems}"


def test_retired_city_gtlds_keep_their_own_place(typed_graph):
    """Retired (undelegated) city gTLDs still carry a full city place with a
    sovereign parent, even though they have left the root zone."""
    by_slug = {p["slug"]: p for p in _places(typed_graph)}
    for slug, parent in (("budapest", "hu"), ("doha", "qa")):
        place = by_slug.get(slug)
        assert place is not None, f"places.json missing retired-city record {slug!r}"
        assert place["subtype"] == "city"
        assert place["parent"] == parent
        assert place["tlds"] == [slug]
        assert typed_graph.tlds[slug].get("delegated") is False


def test_places_sorted_unique_with_envelope(typed_graph):
    """Places are sorted by slug, slugs are unique, and the envelope is present."""
    slugs = [p["slug"] for p in _places(typed_graph)]
    assert slugs == sorted(slugs)
    assert len(slugs) == len(set(slugs))
    assert typed_graph.places["description"]
    assert typed_graph.places["sources"]
