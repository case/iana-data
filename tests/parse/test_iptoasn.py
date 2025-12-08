"""Tests for iptoasn parser."""

from pathlib import Path

from src.parse.iptoasn import ASNLookup, ASNRecord, parse_iptoasn_tsv

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "source" / "iptoasn"


class TestParseIptoasnTsv:
    """Tests for parse_iptoasn_tsv function."""

    def test_parse_combined_sample(self):
        """Test parsing the combined sample TSV file."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        # Should have records from both IPv4 and IPv6 sections
        assert len(records) > 0

    def test_parse_returns_asn_records(self):
        """Test that parser returns ASNRecord objects."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        assert all(isinstance(r, ASNRecord) for r in records)

    def test_parse_ipv4_cloudflare(self):
        """Test parsing Cloudflare IPv4 record (first line)."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        # First record should be Cloudflare
        cloudflare = records[0]
        assert cloudflare.start_ip == "1.0.0.0"
        assert cloudflare.end_ip == "1.0.0.255"
        assert cloudflare.asn == 13335
        assert cloudflare.country == "US"
        assert cloudflare.org == "CLOUDFLARENET"

    def test_parse_ipv4_not_routed(self):
        """Test parsing 'Not routed' record with ASN 0."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        # Second record is "Not routed"
        not_routed = records[1]
        assert not_routed.asn == 0
        assert not_routed.country == "None"
        assert not_routed.org == "Not routed"

    def test_parse_ipv6_google(self):
        """Test parsing Google IPv6 record."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        # Find Google IPv6 record
        google_v6 = next(r for r in records if r.asn == 15169 and ":" in r.start_ip)
        assert google_v6.start_ip == "2c0f:fb50::"
        assert google_v6.country == "US"
        assert google_v6.org == "GOOGLE"

    def test_parse_handles_org_with_spaces(self):
        """Test parsing org names that contain spaces."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        # Find record with multi-word org name
        vectant = next(r for r in records if r.asn == 2519)
        assert vectant.org == "VECTANT ARTERIA Networks Corporation"

    def test_parse_separates_ipv4_and_ipv6(self):
        """Test that both IPv4 and IPv6 records are parsed."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        records = parse_iptoasn_tsv(filepath)

        ipv4_records = [r for r in records if "." in r.start_ip]
        ipv6_records = [r for r in records if ":" in r.start_ip]

        assert len(ipv4_records) > 0
        assert len(ipv6_records) > 0


class TestASNRecord:
    """Tests for ASNRecord dataclass."""

    def test_asn_record_fields(self):
        """Test ASNRecord has expected fields."""
        record = ASNRecord(
            start_ip="1.0.0.0",
            end_ip="1.0.0.255",
            asn=13335,
            country="US",
            org="CLOUDFLARENET",
        )

        assert record.start_ip == "1.0.0.0"
        assert record.end_ip == "1.0.0.255"
        assert record.asn == 13335
        assert record.country == "US"
        assert record.org == "CLOUDFLARENET"

    def test_asn_record_equality(self):
        """Test ASNRecord equality comparison."""
        record1 = ASNRecord("1.0.0.0", "1.0.0.255", 13335, "US", "CLOUDFLARENET")
        record2 = ASNRecord("1.0.0.0", "1.0.0.255", 13335, "US", "CLOUDFLARENET")

        assert record1 == record2


class TestASNLookup:
    """Tests for ASNLookup class."""

    def test_lookup_from_file(self):
        """Test creating lookup from fixture file."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        assert lookup is not None

    def test_lookup_ipv4_cloudflare(self):
        """Test looking up an IPv4 address in Cloudflare range."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("1.0.0.1")
        assert result is not None
        assert result.asn == 13335
        assert result.org == "CLOUDFLARENET"
        assert result.country == "US"

    def test_lookup_ipv4_start_of_range(self):
        """Test looking up first IP in a range."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("1.0.0.0")
        assert result is not None
        assert result.asn == 13335

    def test_lookup_ipv4_end_of_range(self):
        """Test looking up last IP in a range."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("1.0.0.255")
        assert result is not None
        assert result.asn == 13335

    def test_lookup_ipv4_not_routed(self):
        """Test looking up IP in 'Not routed' range returns ASN 0."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("1.0.1.100")
        assert result is not None
        assert result.asn == 0
        assert result.org == "Not routed"

    def test_lookup_ipv6_google(self):
        """Test looking up an IPv6 address in Google range."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("2c0f:fb50::1")
        assert result is not None
        assert result.asn == 15169
        assert result.org == "GOOGLE"

    def test_lookup_ipv6_not_found(self):
        """Test looking up IPv6 not in any range returns None."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        # This IPv6 is before any ranges in our sample
        result = lookup.lookup("2001:db8::1")
        assert result is None

    def test_lookup_ipv4_not_found(self):
        """Test looking up IPv4 not in any range returns None."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        # 0.x.x.x is before any ranges in our sample
        result = lookup.lookup("0.0.0.1")
        assert result is None

    def test_lookup_google_cloud(self):
        """Test looking up IP in Google Cloud range."""
        filepath = FIXTURES_DIR / "ip2asn-combined-sample.tsv"
        lookup = ASNLookup.from_file(filepath)

        result = lookup.lookup("1.179.115.1")
        assert result is not None
        assert result.asn == 396982
        assert result.org == "GOOGLE-CLOUD-PLATFORM"
