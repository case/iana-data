"""Tests for TLD page parser."""

from pathlib import Path

from src.parse.tld_html import parse_tld_page

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "tlds" / "html-partial"


def test_parse_com_tld_display():
    """Test parsing .com TLD display name."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)
    assert result["tld_display"] == "COM"


def test_parse_com_is_generic():
    """Test that .com is identified as generic."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)
    assert result.get("is_generic") is True
    assert "is_cctld" not in result


def test_parse_com_orgs():
    """Test parsing organizations from .com page."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)

    assert "orgs" in result
    assert result["orgs"]["tld_manager"] == "VeriSign Global Registry Services"
    assert result["orgs"]["admin"] == "VeriSign Global Registry Services"
    assert result["orgs"]["tech"] == "VeriSign Global Registry Services"


def test_parse_com_nameservers():
    """Test parsing nameservers from .com page."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)

    assert "nameservers" in result
    assert len(result["nameservers"]) == 13
    assert "a.gtld-servers.net" in result["nameservers"]
    assert "m.gtld-servers.net" in result["nameservers"]


def test_parse_com_registry_info():
    """Test parsing registry information from .com page."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)

    assert result["registry_url"] == "http://www.verisigninc.com"
    assert result["whois_server"] == "whois.verisign-grs.com"
    assert result["rdap_server"] == "https://rdap.verisign.com/com/v1/"


def test_parse_com_dates():
    """Test parsing dates from .com page."""
    html = (FIXTURES_DIR / "com.html").read_text()
    result = parse_tld_page(html)

    assert result["tld_created"] == "1985-01-01"
    assert result["tld_updated"] == "2023-12-07"


def test_parse_tw_is_cctld():
    """Test that .tw is identified as country-code."""
    html = (FIXTURES_DIR / "tw.html").read_text()
    result = parse_tld_page(html)

    assert result.get("is_cctld") is True
    assert "is_generic" not in result


def test_parse_tw_tld_display():
    """Test parsing .tw TLD display name."""
    html = (FIXTURES_DIR / "tw.html").read_text()
    result = parse_tld_page(html)
    assert result["tld_display"] == "TW"


def test_parse_tw_orgs():
    """Test parsing organizations from .tw page."""
    html = (FIXTURES_DIR / "tw.html").read_text()
    result = parse_tld_page(html)

    assert "orgs" in result
    assert result["orgs"]["tld_manager"] == "Taiwan Network Information Center (TWNIC)"
    assert result["orgs"]["admin"] == "Taiwan Network Information Center (TWNIC)"
    assert result["orgs"]["tech"] == "Taiwan Network Information Center (TWNIC)"


def test_parse_tw_nameservers():
    """Test parsing nameservers from .tw page."""
    html = (FIXTURES_DIR / "tw.html").read_text()
    result = parse_tld_page(html)

    assert "nameservers" in result
    assert len(result["nameservers"]) == 9
    assert "a.dns.tw" in result["nameservers"]


def test_parse_idn_traditional_tld_display():
    """Test parsing IDN TLD display name (traditional Chinese)."""
    html = (FIXTURES_DIR / "xn--kpry57d.html").read_text()
    result = parse_tld_page(html)
    assert result["tld_display"] == "台灣"


def test_parse_idn_traditional_tld_iso():
    """Test that IDN ccTLD has tld_iso mapping to TW."""
    html = (FIXTURES_DIR / "xn--kpry57d.html").read_text()
    result = parse_tld_page(html)

    assert result.get("is_cctld") is True
    assert result["tld_iso"] == "tw"


def test_parse_idn_simplified_tld_display():
    """Test parsing IDN TLD display name (simplified Chinese)."""
    html = (FIXTURES_DIR / "xn--kprw13d.html").read_text()
    result = parse_tld_page(html)
    assert result["tld_display"] == "台湾"


def test_parse_idn_simplified_tld_iso():
    """Test that IDN ccTLD (simplified) has tld_iso mapping to TW."""
    html = (FIXTURES_DIR / "xn--kprw13d.html").read_text()
    result = parse_tld_page(html)

    assert result.get("is_cctld") is True
    assert result["tld_iso"] == "tw"


def test_parse_idn_orgs():
    """Test parsing organizations from IDN TLD page."""
    html = (FIXTURES_DIR / "xn--kpry57d.html").read_text()
    result = parse_tld_page(html)

    assert "orgs" in result
    assert result["orgs"]["tld_manager"] == "Taiwan Network Information Center (TWNIC)"


def test_parse_idn_registry_info():
    """Test parsing registry info from IDN TLD page."""
    html = (FIXTURES_DIR / "xn--kpry57d.html").read_text()
    result = parse_tld_page(html)

    assert result["registry_url"] == "http://rs.twnic.net.tw"
    assert result["whois_server"] == "whois.twnic.net.tw"
    assert result["rdap_server"] == "https://ccrdap.twnic.tw/taiwan/"


def test_parse_active_undelegated_no_orgs():
    """Test that undelegated TLD has no organizations."""
    html = (FIXTURES_DIR / "active.html").read_text()
    result = parse_tld_page(html)

    # Undelegated TLDs have empty contact sections
    assert "orgs" not in result or not result.get("orgs")


def test_parse_active_no_nameservers():
    """Test that undelegated TLD has no nameservers."""
    html = (FIXTURES_DIR / "active.html").read_text()
    result = parse_tld_page(html)

    assert "nameservers" not in result


def test_parse_active_multiple_iana_reports():
    """Test parsing multiple IANA reports from .active page."""
    html = (FIXTURES_DIR / "active.html").read_text()
    result = parse_tld_page(html)

    assert "iana_reports" in result
    assert len(result["iana_reports"]) == 2

    # Check delegation report
    delegation = result["iana_reports"][0]
    assert "Delegation" in delegation["title"]
    assert delegation["date"] == "2014-06-23"

    # Check revocation report
    revocation = result["iana_reports"][1]
    assert "Revocation" in revocation["title"]
    assert revocation["date"] == "2019-02-15"


def test_parse_active_dates():
    """Test parsing dates from undelegated .active page."""
    html = (FIXTURES_DIR / "active.html").read_text()
    result = parse_tld_page(html)

    assert result["tld_created"] == "2014-06-19"
    assert result["tld_updated"] == "2019-02-17"


def test_parse_active_is_generic():
    """Test that .active is identified as generic."""
    html = (FIXTURES_DIR / "active.html").read_text()
    result = parse_tld_page(html)

    assert result.get("is_generic") is True


def test_parse_idn_gtld_is_generic():
    """Test that IDN gTLD (परीक्षा) is identified as generic, not ccTLD."""
    html = (FIXTURES_DIR / "xn--11b4c3d.html").read_text()
    result = parse_tld_page(html)

    assert result.get("is_generic") is True
    assert "is_cctld" not in result
    assert "tld_iso" not in result  # No ISO mapping for gTLDs


def test_parse_idn_gtld_tld_display():
    """Test parsing IDN gTLD display name (Devanagari script)."""
    html = (FIXTURES_DIR / "xn--11b4c3d.html").read_text()
    result = parse_tld_page(html)

    assert result["tld_display"] == "कॉम"  # Hindi for "com"
