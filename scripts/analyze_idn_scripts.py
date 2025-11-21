#!/usr/bin/env python3
"""Analyze Unicode scripts used in IDN TLDs.

Uses unicodedata (stdlib) to decode IDN TLDs and identify scripts,
with pycountry to provide canonical ISO 15924 script names.
"""

import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    import pycountry
    HAS_PYCOUNTRY = True
except ImportError:
    HAS_PYCOUNTRY = False


# Mapping from Unicode character name prefixes to ISO 15924 script codes
UNICODE_PREFIX_TO_ISO15924 = {
    "ARABIC": "Arab",
    "ARMENIAN": "Armn",
    "BENGALI": "Beng",
    "CJK": "Hani",  # Han (Hanzi, Kanji, Hanja)
    "CYRILLIC": "Cyrl",
    "DEVANAGARI": "Deva",
    "ETHIOPIC": "Ethi",
    "GEORGIAN": "Geor",
    "GREEK": "Grek",
    "GUJARATI": "Gujr",
    "GURMUKHI": "Guru",
    "HANGUL": "Hang",
    "HEBREW": "Hebr",
    "HIRAGANA": "Hira",
    "KANNADA": "Knda",
    "KATAKANA": "Kana",
    "KHMER": "Khmr",
    "LAO": "Laoo",
    "LATIN": "Latn",
    "MALAYALAM": "Mlym",
    "MONGOLIAN": "Mong",
    "MYANMAR": "Mymr",
    "ORIYA": "Orya",
    "SINHALA": "Sinh",
    "TAMIL": "Taml",
    "TELUGU": "Telu",
    "THAANA": "Thaa",
    "THAI": "Thai",
    "TIBETAN": "Tibt",
}


def get_canonical_script_name(iso_code: str) -> str:
    """Get canonical script name from ISO 15924 code.

    Args:
        iso_code: ISO 15924 4-letter code (e.g., "Grek", "Arab")

    Returns:
        Canonical script name (e.g., "Greek", "Arabic")
    """
    if not HAS_PYCOUNTRY:
        return iso_code

    try:
        script = pycountry.scripts.get(alpha_4=iso_code)
        return script.name if script else iso_code
    except Exception:
        return iso_code


def extract_script_from_char_name(char_name: str) -> tuple[str, str]:
    """Extract canonical script name from Unicode character name.

    Args:
        char_name: Unicode character name (e.g., "GREEK SMALL LETTER ALPHA")

    Returns:
        Tuple of (ISO 15924 code, formal script name)
        e.g., ("Grek", "Greek") or ("Zzzz", "Unknown")
    """
    # Check for CJK ideographs
    if "CJK" in char_name or "IDEOGRAPH" in char_name:
        return ("Hani", get_canonical_script_name("Hani"))

    # Check for script prefixes in character name
    for prefix, iso_code in UNICODE_PREFIX_TO_ISO15924.items():
        if prefix in char_name:
            return (iso_code, get_canonical_script_name(iso_code))

    # Handle special cases
    if char_name.startswith("DIGIT"):
        return ("Zyyy", "Common")
    if char_name in ("HYPHEN-MINUS", "FULL STOP", "HYPHEN"):
        return ("Zyyy", "Common")

    return ("Zzzz", "Unknown")


def analyze_tld(tld: str) -> dict:
    """Analyze scripts used in a single IDN TLD.

    Args:
        tld: ASCII-encoded IDN TLD (e.g., "xn--mgbaam7a8h")

    Returns:
        dict with tld, unicode, and script info
    """
    try:
        # Decode from punycode to Unicode
        unicode_tld = tld.encode("ascii").decode("idna")
    except Exception as e:
        return {
            "tld": tld,
            "unicode": None,
            "error": str(e),
            "scripts": [],
        }

    # Analyze each character
    char_scripts = []
    for char in unicode_tld:
        if char == ".":
            continue

        try:
            char_name = unicodedata.name(char)
            iso_code, script_name = extract_script_from_char_name(char_name)
            char_scripts.append({
                "char": char,
                "name": char_name,
                "iso_code": iso_code,
                "script": script_name,
            })
        except ValueError:
            # Character has no name
            char_scripts.append({
                "char": char,
                "name": None,
                "iso_code": "Zzzz",
                "script": "Unknown",
            })

    # Determine primary script (most common)
    script_counts = Counter(c["script"] for c in char_scripts)
    primary_script = script_counts.most_common(1)[0][0] if script_counts else "Unknown"

    # Get ISO code for primary script
    primary_iso = next(
        (c["iso_code"] for c in char_scripts if c["script"] == primary_script),
        "Zzzz"
    )

    return {
        "tld": tld,
        "unicode": unicode_tld,
        "scripts": char_scripts,
        "primary_script": primary_script,
        "primary_iso": primary_iso,
        "script_counts": dict(script_counts),
    }


def main():
    """Analyze all IDN TLDs and show script statistics."""
    # Read TLD list
    tlds_file = Path("data/source/iana-tlds.txt")
    if not tlds_file.exists():
        print(f"Error: {tlds_file} not found")
        print("Run 'make download-core' first")
        return 1

    # Find all IDN TLDs (start with xn--)
    idn_tlds = []
    with open(tlds_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip().lower()
            if line.startswith("xn--"):
                idn_tlds.append(line)

    print(f"Found {len(idn_tlds)} IDN TLDs\n")

    # Analyze each IDN TLD
    results = []
    script_to_tlds = defaultdict(list)

    for tld in idn_tlds:
        result = analyze_tld(tld)
        results.append(result)

        if result.get("unicode"):
            script_to_tlds[result["primary_script"]].append(result)

    # Print summary by script
    print("=" * 80)
    print("IDN TLDs by Script")
    print("=" * 80)
    print()

    for script in sorted(script_to_tlds.keys()):
        tlds = script_to_tlds[script]
        iso_code = tlds[0]["primary_iso"]  # Get ISO code from first TLD
        print(f"{iso_code:5s} {script}: {len(tlds)} TLDs")
        print("-" * 50)

        # Show first 5 examples
        for result in tlds[:5]:
            unicode_tld = result["unicode"]
            ascii_tld = result["tld"]
            print(f"  {unicode_tld:20s} ({ascii_tld})")

        if len(tlds) > 5:
            print(f"  ... and {len(tlds) - 5} more")
        print()

    # Print detailed view for interesting examples
    print("=" * 80)
    print("Detailed Character Analysis (First 10 IDNs)")
    print("=" * 80)
    print()

    for result in results[:10]:
        if not result.get("unicode"):
            continue

        print(f"TLD: {result['tld']}")
        print(f"Unicode: {result['unicode']}")
        print(f"Primary Script: {result['primary_iso']} - {result['primary_script']}")
        print("Characters:")

        for char_info in result["scripts"]:
            char = char_info["char"]
            name = char_info["name"] or "NO NAME"
            iso_code = char_info["iso_code"]
            script = char_info["script"]
            print(f"  '{char}' → {name} [{iso_code} - {script}]")

        print()

    # Print script statistics
    print("=" * 80)
    print("Script Statistics")
    print("=" * 80)
    print()

    # Build dict of (script_name, iso_code) -> count
    script_data = {}
    for result in results:
        if result.get("unicode"):
            script_name = result["primary_script"]
            iso_code = result["primary_iso"]
            key = (iso_code, script_name)
            script_data[key] = script_data.get(key, 0) + 1

    # Sort by count descending
    sorted_scripts = sorted(script_data.items(), key=lambda x: x[1], reverse=True)

    for (iso_code, script_name), count in sorted_scripts:
        percentage = (count / len(idn_tlds)) * 100
        print(f"{iso_code:5s} {script_name:30s}: {count:3d} TLDs ({percentage:5.1f}%)")

    return 0


if __name__ == "__main__":
    exit(main())
