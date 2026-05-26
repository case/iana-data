"""Derive language_code (BCP-47) and language_name_en for IDN TLDs."""

from typing import Final

# tld_script -> BCP-47 default. Source: CLDR likelySubtags und-<Script>.
# https://www.unicode.org/cldr/charts/latest/supplemental/likely_subtags.html
SCRIPT_LANGUAGE_DEFAULTS: Final[dict[str, str]] = {
    "Arabic": "ar",
    "Armenian": "hy",
    "Bengali": "bn",
    "Cyrillic": "ru",
    "Devanagari": "hi",
    "Georgian": "ka",
    "Greek": "el",
    "Gujarati": "gu",
    "Gurmukhi": "pa",
    "Han-CJK": "zh",
    "Hangul": "ko",
    "Hebrew": "he",
    "Hiragana": "ja",
    "Kannada": "kn",
    "Katakana": "ja",
    "Lao": "lo",
    "Malayalam": "ml",
    "Oriya": "or",
    "Sinhala": "si",
    "Tamil": "ta",
    "Telugu": "te",
    "Thai": "th",
}

# (tld_script, tld_iso) -> BCP-47. Source: CLDR likelySubtags und-<Script>-<Region>.
# Deviations pinned in tests/build/test_idn_language_provenance.py.
SCRIPT_REGION_LANGUAGES: Final[dict[tuple[str, str], str]] = {
    ("Cyrillic", "bg"): "bg",
    ("Cyrillic", "by"): "be",
    ("Cyrillic", "eu"): "bg",
    ("Cyrillic", "kz"): "kk",
    ("Cyrillic", "mk"): "mk",
    ("Cyrillic", "mn"): "mn",
    ("Cyrillic", "rs"): "sr",
    ("Cyrillic", "ua"): "uk",
    ("Arabic", "ir"): "fa",
    ("Arabic", "my"): "ms",
    ("Arabic", "pk"): "ur",
}

# BCP-47 code -> English name. Codes per IANA registry:
# https://www.iana.org/assignments/language-subtag-registry
LANGUAGE_NAMES_EN: Final[dict[str, str]] = {
    "ar": "Arabic",
    "as": "Assamese",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",  # CLDR uses "Bangla"; "Bengali" is older English convention
    "brx": "Bodo",
    "de": "German",
    "el": "Greek",
    "fa": "Persian",
    "gu": "Gujarati",
    "he": "Hebrew",
    "hi": "Hindi",
    "hy": "Armenian",
    "ja": "Japanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "kn": "Kannada",
    "ko": "Korean",
    "lo": "Lao",
    "mai": "Maithili",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "mn": "Mongolian",
    "ms": "Malay",
    "or": "Odia",
    "pa": "Punjabi",
    "ru": "Russian",
    "sa": "Sanskrit",
    "sd": "Sindhi",
    "si": "Sinhala",
    "sr": "Serbian",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "zh": "Chinese",
    "zh-Hans": "Chinese (Simplified)",
    "zh-Hant": "Chinese (Traditional)",
    "zh-Hant-TW": "Chinese (Taiwan)",  # CLDR: "Chinese (Traditional, Taiwan)"
}


def derive_language(
    tld_script: str | None,
    tld_iso: str | None,
    manual_language_code: str | None,
) -> tuple[str, str] | None:
    """Return ``(language_code, language_name_en)``, or ``None`` if no script.

    Resolution: manual override > region table > script default. Raises
    ``ValueError`` for an unmapped ``tld_script`` or ``language_code``.
    """
    if manual_language_code:
        code = manual_language_code
    elif tld_script is None:
        return None
    else:
        iso = tld_iso.lower() if tld_iso else None
        if iso and (tld_script, iso) in SCRIPT_REGION_LANGUAGES:
            code = SCRIPT_REGION_LANGUAGES[(tld_script, iso)]
        elif tld_script in SCRIPT_LANGUAGE_DEFAULTS:
            code = SCRIPT_LANGUAGE_DEFAULTS[tld_script]
        else:
            raise ValueError(
                f"No language mapping for tld_script={tld_script!r}; "
                f"add it to SCRIPT_LANGUAGE_DEFAULTS in src/build/idn_language.py"
            )

    name = LANGUAGE_NAMES_EN.get(code)
    if name is None:
        raise ValueError(
            f"No English name for language_code={code!r}; "
            f"add it to LANGUAGE_NAMES_EN in src/build/idn_language.py"
        )
    return code, name
