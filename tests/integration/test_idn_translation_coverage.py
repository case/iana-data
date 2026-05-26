"""Every delegated IDN TLD must have at least one English-meaning source.

A new IDN delegation that slips through ICANN's Translation column AND isn't
tagged geographic/cultural AND isn't a country-code IDN would be uncovered.
This test fails loudly when that happens so a curator knows to either tag it
or add a manual ``icann_translation_en`` override in ``annotations.json``.
"""


def _english_sources(
    tld: str, entry: dict, places_by_tld: dict, cultures_by_slug: dict
) -> list[str]:
    """All layers carrying an English meaning for this IDN."""
    sources = []
    annotations = entry.get("annotations", {})
    if annotations.get("icann_translation_en"):
        sources.append("icann_translation_en")
    if annotations.get("geographic_scope") and tld in places_by_tld:
        sources.append(f"place:{places_by_tld[tld]}")
    if (slug := annotations.get("cultural_affiliation")) and slug in cultures_by_slug:
        sources.append(f"culture:{slug}")
    if entry.get("iana_tag") == "country-code" and entry.get("tld_iso"):
        sources.append(f"country:{entry['tld_iso']}")
    return sources


def test_every_idn_has_an_english_meaning(typed_graph):
    """Every delegated IDN resolves to an English string through at least one
    of: ICANN translation, geographic_scope -> place, cultural_affiliation ->
    culture, or country-code -> tld_iso country."""
    places_by_tld = {
        tld: p["slug"] for p in typed_graph.places["places"] for tld in p["tlds"]
    }
    cultures_by_slug = {c["slug"]: c for c in typed_graph.cultures["cultures"]}

    uncovered = []
    for tld, entry in typed_graph.tlds.items():
        if not entry.get("delegated") or not tld.startswith("xn--"):
            continue
        if not _english_sources(tld, entry, places_by_tld, cultures_by_slug):
            uncovered.append((tld, entry.get("tld_unicode")))

    assert uncovered == [], (
        "delegated IDN TLDs with no English-meaning source "
        "(add icann_translation_en in annotations.json, or tag geographic/cultural): "
        f"{uncovered}"
    )
