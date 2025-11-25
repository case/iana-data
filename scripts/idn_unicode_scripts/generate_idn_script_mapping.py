#!/usr/bin/env python3
"""Generate IDN script mappings.

Creates data/generated/idn-script-mapping.json with mappings of IDN TLDs to their scripts.
This is generated once since IDN scripts don't change.
"""

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import IDN_SCRIPT_MAPPING_FILE
from src.parse.root_db_html import parse_root_db_html

try:
    import pycountry

    HAS_PYCOUNTRY = True
except ImportError:
    HAS_PYCOUNTRY = False
    print("Warning: pycountry not available, using ISO codes instead of names")


# Mapping from Unicode character name prefixes to ISO 15924 script codes
UNICODE_PREFIX_TO_ISO15924 = {
    "ARABIC": "Arab",
    "ARMENIAN": "Armn",
    "BENGALI": "Beng",
    "CJK": "Hani",
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
    """Get canonical script name from ISO 15924 code."""
    if not HAS_PYCOUNTRY:
        return iso_code

    try:
        script = pycountry.scripts.get(alpha_4=iso_code)
        return script.name if script else iso_code
    except Exception:
        return iso_code


def normalize_script_name(script_name: str) -> str:
    """Normalize script name by removing parenthetical alternates.

    Rules:
    1. "Han (Hanzi, Kanji, Hanja)" -> "Han-CJK"
    2. Strip everything in parentheses for others
    """
    # Special case: Han -> Han-CJK
    if script_name == "Han (Hanzi, Kanji, Hanja)":
        return "Han-CJK"

    # Strip parenthetical alternates
    if "(" in script_name:
        return script_name.split("(")[0].strip()

    return script_name


def detect_script(char_name: str) -> str:
    """Detect script from Unicode character name."""
    # Check for CJK ideographs
    if "CJK" in char_name or "IDEOGRAPH" in char_name:
        full_name = get_canonical_script_name("Hani")
        return normalize_script_name(full_name)

    # Check for script prefixes
    for prefix, iso_code in UNICODE_PREFIX_TO_ISO15924.items():
        if prefix in char_name:
            full_name = get_canonical_script_name(iso_code)
            return normalize_script_name(full_name)

    return "Unknown"


def detect_tld_script(tld: str) -> str | None:
    """Detect the primary script used in an IDN TLD."""
    try:
        # Decode from punycode to Unicode
        unicode_tld = tld.encode("ascii").decode("idna")
    except Exception:
        return None

    # Analyze each character's script
    char_scripts = []
    for char in unicode_tld:
        if char == ".":
            continue

        try:
            char_name = unicodedata.name(char)
            script_name = detect_script(char_name)
            if script_name != "Unknown":
                char_scripts.append(script_name)
        except ValueError:
            # Character has no name
            continue

    if not char_scripts:
        return None

    # Return most common script
    script_counts = Counter(char_scripts)
    return script_counts.most_common(1)[0][0]


def main():
    """Generate IDN script mappings."""
    # Parse root zone database to get all TLDs (delegated and undelegated)
    print("Parsing root zone database...")
    try:
        root_zone_entries = parse_root_db_html()
    except Exception as e:
        print(f"Error parsing root zone database: {e}")
        print("Run 'make download-core' first")
        return 1

    # Find all IDN TLDs (starting with xn--)
    idn_tlds = []
    for entry in root_zone_entries:
        tld = entry["domain"].lstrip(".")
        if tld.startswith("xn--"):
            idn_tlds.append(tld)

    print(f"Found {len(idn_tlds)} IDN TLDs (delegated and undelegated)")

    # Generate mappings
    mappings = {}
    for tld in idn_tlds:
        script = detect_tld_script(tld)
        if script:
            mappings[tld] = script

    print(f"Generated {len(mappings)} script mappings")

    # Show distribution
    script_counts = Counter(mappings.values())
    print("\nScript distribution:")
    for script, count in script_counts.most_common():
        print(f"  {script:20s}: {count:3d} TLDs")

    # Write output
    output_file = Path(IDN_SCRIPT_MAPPING_FILE)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mappings, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nWrote mappings to {output_file}")
    return 0


if __name__ == "__main__":
    exit(main())
