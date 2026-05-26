"""Pin SCRIPT_LANGUAGE_DEFAULTS / SCRIPT_REGION_LANGUAGES to CLDR likelySubtags."""

from langcodes import Language, tag_is_valid

from src.build.idn_language import (
    LANGUAGE_NAMES_EN,
    SCRIPT_LANGUAGE_DEFAULTS,
    SCRIPT_REGION_LANGUAGES,
)

# Our internal Unicode-script labels -> ISO 15924 4-letter codes that CLDR uses.
SCRIPT_ISO_CODES: dict[str, str] = {
    "Arabic": "Arab",
    "Armenian": "Armn",
    "Bengali": "Beng",
    "Cyrillic": "Cyrl",
    "Devanagari": "Deva",
    "Georgian": "Geor",
    "Greek": "Grek",
    "Gujarati": "Gujr",
    "Gurmukhi": "Guru",
    "Han-CJK": "Hani",
    "Hangul": "Hang",
    "Hebrew": "Hebr",
    "Hiragana": "Hira",
    "Kannada": "Knda",
    "Katakana": "Kana",
    "Lao": "Laoo",
    "Malayalam": "Mlym",
    "Oriya": "Orya",
    "Sinhala": "Sinh",
    "Tamil": "Taml",
    "Telugu": "Telu",
    "Thai": "Thai",
}

# (script, region) -> (our value, CLDR-resolved value) for documented overrides.
EDITORIAL_REGION_DEVIATIONS: dict[tuple[str, str], tuple[str, str]] = {
    # Bulgaria is the only Cyrillic-script EU member; .ею is Bulgarian.
    ("Cyrillic", "eu"): ("bg", "en"),
    # .қаз is the Kazakh-language ccTLD; CLDR's "ru" reflects KZ demography.
    ("Cyrillic", "kz"): ("kk", "ru"),
}


def test_script_defaults_match_cldr_likelysubtags():
    for script, expected in SCRIPT_LANGUAGE_DEFAULTS.items():
        iso = SCRIPT_ISO_CODES.get(script)
        assert iso, (
            f"Add ISO 15924 mapping for {script!r} in SCRIPT_ISO_CODES "
            f"(provenance test)"
        )
        cldr = Language.get(f"und-{iso}").maximize().language
        assert cldr == expected, (
            f"SCRIPT_LANGUAGE_DEFAULTS[{script!r}] = {expected!r} but CLDR "
            f"likelySubtags resolves und-{iso} to {cldr!r}. Correct the table "
            f"or document an editorial override."
        )


def test_region_overrides_match_cldr_except_documented():
    for (script, region), expected in SCRIPT_REGION_LANGUAGES.items():
        iso = SCRIPT_ISO_CODES[script]
        cldr = Language.get(f"und-{iso}-{region.upper()}").maximize().language
        documented = EDITORIAL_REGION_DEVIATIONS.get((script, region))
        if documented is not None:
            assert (expected, cldr) == documented, (
                f"Editorial deviation drift at ({script!r}, {region!r}): "
                f"table now {expected!r}/CLDR now {cldr!r}, documented as "
                f"{documented[0]!r}/{documented[1]!r}."
            )
        else:
            assert cldr == expected, (
                f"SCRIPT_REGION_LANGUAGES[({script!r}, {region!r})] = "
                f"{expected!r} but CLDR resolves to {cldr!r}. Correct the "
                f"table or add to EDITORIAL_REGION_DEVIATIONS with a reason."
            )


def test_language_names_keys_are_valid_bcp47():
    for code in LANGUAGE_NAMES_EN:
        assert tag_is_valid(code), (
            f"LANGUAGE_NAMES_EN key {code!r} is not a valid BCP-47 tag"
        )


def test_every_referenced_code_has_an_english_name():
    referenced = set(SCRIPT_LANGUAGE_DEFAULTS.values()) | set(
        SCRIPT_REGION_LANGUAGES.values()
    )
    missing = referenced - set(LANGUAGE_NAMES_EN)
    assert not missing, (
        f"Codes referenced in defaults/regions are missing from "
        f"LANGUAGE_NAMES_EN: {sorted(missing)}"
    )
