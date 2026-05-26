"""Every delegated IDN must carry ``language_code`` and ``language_name_en``."""


def test_every_delegated_idn_has_language_fields(typed_graph):
    uncovered = []
    for tld, entry in typed_graph.tlds.items():
        if not entry.get("delegated") or not tld.startswith("xn--"):
            continue
        annotations = entry.get("annotations", {})
        if not annotations.get("language_code") or not annotations.get(
            "language_name_en"
        ):
            uncovered.append((tld, entry.get("tld_unicode"), entry.get("tld_script")))

    assert uncovered == [], (
        "delegated IDN TLDs missing language_code or language_name_en "
        "(extend SCRIPT_LANGUAGE_DEFAULTS in src/build/idn_language.py, "
        "or add a manual language_code in data/manual/annotations.json): "
        f"{uncovered}"
    )
