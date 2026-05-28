"""Tests for src.build.idn_language.derive_language."""

import pytest

from src.build.idn_language import derive_language


def test_script_default_for_gtld():
    assert derive_language("Arabic", None, None) == ("ar", "Arabic")


def test_script_default_for_cctld_without_region_override():
    assert derive_language("Cyrillic", "ru", None) == ("ru", "Russian")


def test_region_override_cyrillic_bulgaria():
    assert derive_language("Cyrillic", "bg", None) == ("bg", "Bulgarian")


def test_region_override_arabic_iran():
    assert derive_language("Arabic", "ir", None) == ("fa", "Persian")


def test_devanagari_default_is_hindi():
    assert derive_language("Devanagari", "in", None) == ("hi", "Hindi")


def test_tamil_script_resolves_to_tamil_in_india():
    assert derive_language("Tamil", "in", None) == ("ta", "Tamil")


def test_han_default_is_chinese_across_region():
    assert derive_language("Han-CJK", "cn", None) == ("zh", "Chinese")
    assert derive_language("Han-CJK", "tw", None) == ("zh", "Chinese")


def test_manual_override_wins_over_script_default():
    assert derive_language("Arabic", "in", "sd") == ("sd", "Sindhi")


def test_manual_override_wins_over_region_override():
    assert derive_language("Cyrillic", "kz", "ru") == ("ru", "Russian")


def test_returns_none_for_non_idn():
    assert derive_language(None, None, None) is None
    assert derive_language(None, "us", None) is None


def test_unknown_script_raises():
    with pytest.raises(ValueError, match="No language mapping for tld_script"):
        derive_language("Mystery", None, None)


def test_unknown_manual_language_code_raises():
    with pytest.raises(ValueError, match="No English name for language_code"):
        derive_language("Arabic", "ae", "xyz")


def test_tld_iso_uppercase_still_hits_region_override():
    assert derive_language("Cyrillic", "BG", None) == ("bg", "Bulgarian")
    assert derive_language("Arabic", "IR", None) == ("fa", "Persian")


def test_chinese_variant_overrides():
    assert derive_language("Han-CJK", "cn", "zh-Hans") == (
        "zh-Hans",
        "Chinese (Simplified)",
    )
    assert derive_language("Han-CJK", "cn", "zh-Hant") == (
        "zh-Hant",
        "Chinese (Traditional)",
    )
    assert derive_language("Han-CJK", "tw", "zh-Hant-TW") == (
        "zh-Hant-TW",
        "Chinese (Taiwan)",
    )
