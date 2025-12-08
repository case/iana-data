"""Tests for IDN script field in tlds.json."""

import json
from pathlib import Path

import pytest

from src.build.tlds import build_tlds_json
from src.config import FIXTURES_DIR, FIXTURES_FILES


@pytest.fixture
def built_tlds_json(tmp_path, monkeypatch):
    """Build tlds.json in temp directory using fixture mapping."""
    mapping_fixture = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]
    monkeypatch.setattr("src.build.tlds.TLDS_OUTPUT_FILE", str(tmp_path / "tlds.json"))
    monkeypatch.setattr("src.build.tlds.IDN_SCRIPT_MAPPING_FILE", str(mapping_fixture))
    monkeypatch.setattr("src.utilities.metadata.METADATA_FILE", str(tmp_path / "metadata.json"))
    build_tlds_json()

    with open(tmp_path / "tlds.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_idn_script_mapping_fixture_exists():
    """Test that IDN script mapping fixture exists."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]
    assert mapping_file.exists(), f"IDN script mapping fixture not found: {mapping_file}"


def test_idn_script_mapping_file_format():
    """Test that IDN script mapping file has correct format."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]

    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)

    assert isinstance(mappings, dict)
    assert len(mappings) > 0

    # Check that all keys are IDN TLDs
    for tld in mappings.keys():
        assert tld.startswith("xn--"), f"Non-IDN TLD in mapping: {tld}"

    # Check that all values are strings
    for script in mappings.values():
        assert isinstance(script, str)
        assert len(script) > 0


def test_idn_script_mapping_has_expected_scripts():
    """Test that mapping includes expected script names."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]

    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)

    scripts = set(mappings.values())

    # Check for major expected scripts
    expected_scripts = {
        "Han-CJK",  # Custom override
        "Arabic",
        "Cyrillic",
        "Greek",
        "Devanagari",
    }

    for script in expected_scripts:
        assert script in scripts, f"Expected script not found: {script}"


def test_han_cjk_override():
    """Test that Han script is renamed to Han-CJK."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]

    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)

    scripts = set(mappings.values())

    # Should have Han-CJK, not "Han" or "Han (Hanzi, Kanji, Hanja)"
    assert "Han-CJK" in scripts
    assert "Han" not in scripts
    assert "Han (Hanzi, Kanji, Hanja)" not in scripts


def test_no_parentheticals_in_script_names():
    """Test that script names don't include parenthetical alternates."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]

    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)

    for script in mappings.values():
        # Exception: Han-CJK is allowed
        if script == "Han-CJK":
            continue
        assert "(" not in script, f"Script has parenthetical: {script}"


def test_tld_script_field_present_for_idns(built_tlds_json):
    """Test that tld_script field is present for IDN TLDs."""
    tlds = built_tlds_json["tlds"]
    idn_tlds = [t for t in tlds if t["tld"].startswith("xn--")]

    assert len(idn_tlds) > 0, "No IDN TLDs found"

    # Load the fixture to provide helpful error messages
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]
    with open(mapping_file, "r", encoding="utf-8") as f:
        fixture_mappings = json.load(f)

    # All IDN TLDs should have tld_script field
    for tld in idn_tlds:
        tld_name = tld['tld']
        if "tld_script" not in tld:
            # Check if it's in the fixture
            if tld_name not in fixture_mappings:
                pytest.fail(
                    f"Missing tld_script for {tld_name}. "
                    f"This TLD is not in the test fixture at {mapping_file}. "
                    f"Run 'make generate-idn-mapping' to update production mapping, "
                    f"then add '{tld_name}' to the test fixture."
                )
            else:
                pytest.fail(f"Missing tld_script for {tld_name} (TLD is in fixture but not in built JSON)")
        assert isinstance(tld["tld_script"], str)
        assert len(tld["tld_script"]) > 0


def test_tld_script_field_absent_for_ascii(built_tlds_json):
    """Test that tld_script field is absent for ASCII TLDs."""
    tlds = built_tlds_json["tlds"]
    ascii_tlds = [t for t in tlds if not t["tld"].startswith("xn--")]

    assert len(ascii_tlds) > 0, "No ASCII TLDs found"

    # ASCII TLDs should not have tld_script field
    for tld in ascii_tlds:
        assert "tld_script" not in tld, f"Unexpected tld_script for {tld['tld']}"


def test_tld_script_matches_mapping_file(built_tlds_json):
    """Test that tld_script values match the mapping file."""
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]

    with open(mapping_file, "r", encoding="utf-8") as f:
        mappings = json.load(f)

    tlds = built_tlds_json["tlds"]
    idn_tlds = [t for t in tlds if t["tld"].startswith("xn--")]

    for tld in idn_tlds:
        tld_name = tld["tld"]
        expected_script = mappings.get(tld_name)

        if expected_script:
            assert tld["tld_script"] == expected_script, (
                f"Script mismatch for {tld_name}: "
                f"expected {expected_script}, got {tld['tld_script']}"
            )


def test_specific_known_scripts(built_tlds_json):
    """Test specific known IDN TLDs have correct scripts."""
    tlds = built_tlds_json["tlds"]
    tld_lookup = {t["tld"]: t for t in tlds}

    test_cases = {
        "xn--qxam": "Greek",  # ελ (Greece)
        "xn--mgbaam7a8h": "Arabic",  # امارات (UAE)
        "xn--node": "Georgian",  # გე (Georgia)
        "xn--3e0b707e": "Hangul",  # 한국 (Korea)
        "xn--fiqs8s": "Han-CJK",  # 中国 (China)
    }

    for tld, expected_script in test_cases.items():
        if tld in tld_lookup:
            assert tld_lookup[tld]["tld_script"] == expected_script, (
                f"Incorrect script for {tld}: "
                f"expected {expected_script}, got {tld_lookup[tld]['tld_script']}"
            )


def test_delegated_and_undelegated_idns_have_scripts(built_tlds_json):
    """Test that both delegated and undelegated IDN TLDs have scripts."""
    tlds = built_tlds_json["tlds"]
    idn_tlds = [t for t in tlds if t["tld"].startswith("xn--")]

    delegated_idns = [t for t in idn_tlds if t["delegated"]]
    undelegated_idns = [t for t in idn_tlds if not t["delegated"]]

    assert len(delegated_idns) > 0, "No delegated IDN TLDs found"
    assert len(undelegated_idns) > 0, "No undelegated IDN TLDs found"

    # Load the fixture to provide helpful error messages
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]
    with open(mapping_file, "r", encoding="utf-8") as f:
        fixture_mappings = json.load(f)

    # All should have scripts
    for tld in delegated_idns:
        if "tld_script" not in tld:
            tld_name = tld['tld']
            if tld_name not in fixture_mappings:
                pytest.fail(
                    f"Delegated IDN {tld_name} missing tld_script. "
                    f"TLD not in test fixture at {mapping_file}. "
                    f"Run 'make generate-idn-mapping' then update test fixture."
                )
        assert tld["tld_script"]

    for tld in undelegated_idns:
        if "tld_script" not in tld:
            tld_name = tld['tld']
            if tld_name not in fixture_mappings:
                pytest.fail(
                    f"Undelegated IDN {tld_name} missing tld_script. "
                    f"TLD not in test fixture at {mapping_file}. "
                    f"Run 'make generate-idn-mapping' then update test fixture."
                )
        assert tld["tld_script"]


def test_no_null_scripts_for_idns(built_tlds_json):
    """Test that no IDN TLDs have null/missing scripts."""
    tlds = built_tlds_json["tlds"]
    idn_tlds = [t for t in tlds if t["tld"].startswith("xn--")]

    # Load the fixture to provide helpful error messages
    mapping_file = Path(FIXTURES_DIR) / FIXTURES_FILES["IDN_SCRIPT_MAPPING"]
    with open(mapping_file, "r", encoding="utf-8") as f:
        fixture_mappings = json.load(f)

    for tld in idn_tlds:
        tld_name = tld['tld']
        if tld.get("tld_script") is None:
            if tld_name not in fixture_mappings:
                pytest.fail(
                    f"Null script for {tld_name}. "
                    f"TLD not in test fixture at {mapping_file}. "
                    f"Run 'make generate-idn-mapping' then update test fixture."
                )
            else:
                pytest.fail(f"Null script for {tld_name} (TLD is in fixture but not in built JSON)")
        assert tld["tld_script"] != "", f"Empty script for {tld_name}"
