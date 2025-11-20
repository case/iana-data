"""Tests for country name lookup module."""

from pathlib import Path

from src.parse.country import get_all_country_mappings, get_country_name, is_cctld
from src.parse.tlds_txt import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "core"


class TestGetCountryName:
    """Tests for get_country_name function."""

    def test_ascii_cctld_lookup(self):
        """Test looking up country names for ASCII ccTLDs."""
        assert get_country_name("us") == "United States"
        assert get_country_name("gb") == "United Kingdom"
        assert get_country_name("de") == "Germany"
        assert get_country_name("jp") == "Japan"
        assert get_country_name("fr") == "France"

    def test_case_insensitive(self):
        """Test that lookups are case-insensitive."""
        assert get_country_name("US") == "United States"
        assert get_country_name("Us") == "United States"
        assert get_country_name("us") == "United States"

    def test_override_ac(self):
        """Test Ascension Island override (not in ISO 3166-1)."""
        assert get_country_name("ac") == "Ascension Island"

    def test_override_eu(self):
        """Test European Union override (not a country)."""
        assert get_country_name("eu") == "European Union"

    def test_override_su(self):
        """Test Soviet Union override (historical)."""
        assert get_country_name("su") == "Soviet Union"

    def test_override_uk(self):
        """Test United Kingdom override (ISO uses GB)."""
        assert get_country_name("uk") == "United Kingdom"

    def test_gtld_returns_none(self):
        """Test that gTLDs return None."""
        assert get_country_name("com") is None
        assert get_country_name("org") is None
        assert get_country_name("net") is None

    def test_invalid_code_returns_none(self):
        """Test that invalid codes return None."""
        assert get_country_name("xx") is None
        assert get_country_name("zz") is None


class TestIsCctld:
    """Tests for is_cctld function."""

    def test_ascii_cctld(self):
        """Test that 2-letter codes are identified as ccTLDs."""
        assert is_cctld("us") is True
        assert is_cctld("gb") is True
        assert is_cctld("de") is True

    def test_gtld_not_cctld(self):
        """Test that gTLDs are not identified as ccTLDs."""
        assert is_cctld("com") is False
        assert is_cctld("org") is False
        assert is_cctld("info") is False

    def test_idn_not_cctld(self):
        """Test that IDN TLDs are not identified as ccTLDs by this function."""
        # IDN ccTLDs start with xn-- so they fail the 2-letter check
        assert is_cctld("xn--wgbh1c") is False
        assert is_cctld("xn--2scrj9c") is False

    def test_single_letter_not_cctld(self):
        """Test that single letter codes are not ccTLDs."""
        assert is_cctld("a") is False


class TestGetAllCountryMappings:
    """Tests for get_all_country_mappings function."""

    def test_returns_dict(self):
        """Test that function returns a dictionary."""
        fixture_path = FIXTURES_DIR / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)
        mappings = get_all_country_mappings(tlds)
        assert isinstance(mappings, dict)

    def test_only_includes_cctlds(self):
        """Test that only ccTLDs are included in mappings."""
        fixture_path = FIXTURES_DIR / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)
        mappings = get_all_country_mappings(tlds)

        # Should only have 2-letter keys
        for key in mappings:
            assert len(key) == 2

    def test_mappings_have_country_names(self):
        """Test that all mappings have country names."""
        fixture_path = FIXTURES_DIR / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)
        mappings = get_all_country_mappings(tlds)

        for code, name in mappings.items():
            assert isinstance(name, str)
            assert len(name) > 0

    def test_real_data_coverage(self):
        """Test that we can map all ccTLDs from real data."""
        # Use default path (real data)
        tlds = parse_tlds_txt()
        mappings = get_all_country_mappings(tlds)

        # Should have 248 ccTLDs mapped
        assert len(mappings) == 248

        # Spot check some mappings
        assert mappings["us"] == "United States"
        assert mappings["uk"] == "United Kingdom"
        assert mappings["eu"] == "European Union"
