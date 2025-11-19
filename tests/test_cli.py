"""Tests for CLI module."""

import sys
from pathlib import Path
from unittest.mock import patch

from src.cli import main
from src.parse import parse_tlds_txt

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestDownloadCommand:
    """Tests for --download command."""

    def test_download_all_sources_success(self):
        """Test downloading all sources successfully."""
        mock_results = {
            "RDAP_BOOTSTRAP": "downloaded",
            "TLD_LIST": "not_modified",
            "ROOT_ZONE_DB": "downloaded",
        }

        with patch("src.cli.download_iana_files", return_value=mock_results):
            with patch.object(sys, "argv", ["cli", "--download"]):
                result = main()

        assert result == 0

    def test_download_specific_source_success(self):
        """Test downloading a specific source."""
        mock_results = {"TLD_LIST": "downloaded"}

        with patch("src.cli.download_iana_files", return_value=mock_results):
            with patch.object(sys, "argv", ["cli", "--download", "TLD_LIST"]):
                result = main()

        assert result == 0

    def test_download_with_error(self):
        """Test download returns error code on failure."""
        mock_results = {
            "RDAP_BOOTSTRAP": "downloaded",
            "TLD_LIST": "error",
            "ROOT_ZONE_DB": "downloaded",
        }

        with patch("src.cli.download_iana_files", return_value=mock_results):
            with patch.object(sys, "argv", ["cli", "--download"]):
                result = main()

        assert result == 1

    def test_download_invalid_source(self):
        """Test download with invalid source name."""
        with patch.object(sys, "argv", ["cli", "--download", "INVALID_SOURCE"]):
            result = main()

        assert result == 1


class TestDownloadTldPagesCommand:
    """Tests for --download-tld-pages command."""

    def test_download_tld_pages_with_prefix(self):
        """Test downloading TLD pages with prefix filter."""
        mock_tlds = ["aaa", "aarp", "abb"]
        mock_results = {"aaa": "downloaded", "aarp": "downloaded", "abb": "downloaded"}

        with (
            patch("src.cli.parse_tlds_txt", return_value=mock_tlds),
            patch("src.cli.download_tld_pages", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "a"]),
        ):
            result = main()

        assert result == 0

    def test_download_tld_pages_with_errors(self):
        """Test download TLD pages returns error on failures."""
        mock_tlds = ["com", "net"]
        mock_results = {"com": "downloaded", "net": "error"}

        with (
            patch("src.cli.parse_tlds_txt", return_value=mock_tlds),
            patch("src.cli.download_tld_pages", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "c", "n"]),
        ):
            result = main()

        assert result == 1

    def test_download_tld_pages_no_tlds_found(self):
        """Test download TLD pages when no TLDs are found."""
        with (
            patch("src.cli.parse_tlds_txt", return_value=[]),
            patch.object(sys, "argv", ["cli", "--download-tld-pages"]),
        ):
            result = main()

        assert result == 1

    def test_download_tld_pages_no_matching_prefix(self):
        """Test download TLD pages when no TLDs match prefix."""
        mock_tlds = ["com", "net", "org"]

        with (
            patch("src.cli.parse_tlds_txt", return_value=mock_tlds),
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "z"]),
        ):
            result = main()

        assert result == 0  # No error, just no TLDs to download

    def test_download_tld_pages_x_prefix_excludes_xn(self):
        """Test that 'x' prefix doesn't match 'xn--' TLDs unless explicitly specified."""
        fixture_path = FIXTURES_DIR / "source" / "core" / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)

        # Fixture contains: xbox, xyz, xn--2scrj9c, xn--4dbrk0ce, xn--flw351e, xn--kpry57d, xn--wgbh1c
        x_tlds = [t for t in tlds if t.startswith("x")]
        xn_tlds = [t for t in tlds if t.startswith("xn--")]
        non_xn_x_tlds = [t for t in x_tlds if not t.startswith("xn--")]

        # Verify fixture has the expected TLDs
        assert len(non_xn_x_tlds) == 2  # xbox, xyz
        assert len(xn_tlds) == 5

        with (
            patch("src.cli.parse_tlds_txt", return_value=tlds),
            patch("src.cli.download_tld_pages") as mock_download,
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "x"]),
        ):
            mock_download.return_value = {t: "downloaded" for t in non_xn_x_tlds}
            result = main()

        # Should only download non-IDN x TLDs
        assert result == 0
        mock_download.assert_called_once()
        downloaded_tlds = mock_download.call_args[0][0]
        assert "xbox" in downloaded_tlds
        assert "xyz" in downloaded_tlds
        # xn-- TLDs should NOT be included
        for xn_tld in xn_tlds:
            assert xn_tld not in downloaded_tlds

    def test_download_tld_pages_xn_prefix_explicit(self):
        """Test that 'xn--' prefix explicitly downloads IDN TLDs."""
        fixture_path = FIXTURES_DIR / "source" / "core" / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)
        xn_tlds = [t for t in tlds if t.startswith("xn--")]

        with (
            patch("src.cli.parse_tlds_txt", return_value=tlds),
            patch("src.cli.download_tld_pages") as mock_download,
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "xn--"]),
        ):
            mock_download.return_value = {t: "downloaded" for t in xn_tlds}
            result = main()

        # Should only download xn-- TLDs
        assert result == 0
        mock_download.assert_called_once()
        downloaded_tlds = mock_download.call_args[0][0]
        assert "xbox" not in downloaded_tlds
        assert "xyz" not in downloaded_tlds
        for xn_tld in xn_tlds:
            assert xn_tld in downloaded_tlds

    def test_download_tld_pages_x_and_xn_prefix_together(self):
        """Test that 'x' and 'xn--' together downloads all x TLDs."""
        fixture_path = FIXTURES_DIR / "source" / "core" / "tlds.txt"
        tlds = parse_tlds_txt(fixture_path)
        all_x_tlds = [t for t in tlds if t.startswith("x")]

        with (
            patch("src.cli.parse_tlds_txt", return_value=tlds),
            patch("src.cli.download_tld_pages") as mock_download,
            patch.object(sys, "argv", ["cli", "--download-tld-pages", "x", "xn--"]),
        ):
            mock_download.return_value = {t: "downloaded" for t in all_x_tlds}
            result = main()

        # Should download all x TLDs including xn--
        assert result == 0
        mock_download.assert_called_once()
        downloaded_tlds = mock_download.call_args[0][0]
        assert len(downloaded_tlds) == 7  # 2 non-IDN + 5 IDN
        assert "xbox" in downloaded_tlds
        assert "xyz" in downloaded_tlds
        for xn_tld in [t for t in tlds if t.startswith("xn--")]:
            assert xn_tld in downloaded_tlds


class TestAnalyzeCommand:
    """Tests for --analyze command."""

    def test_analyze_all_files_success(self):
        """Test analyzing all files successfully."""
        with (
            patch("src.cli.analyze_tlds_txt", return_value=0),
            patch("src.cli.analyze_root_db_html", return_value=0),
            patch("src.cli.analyze_rdap_json", return_value=0),
            patch.object(sys, "argv", ["cli", "--analyze"]),
        ):
            result = main()

        assert result == 0

    def test_analyze_specific_file_success(self):
        """Test analyzing a specific file."""
        with (
            patch("src.cli.analyze_tlds_txt", return_value=0),
            patch.object(sys, "argv", ["cli", "--analyze", "tlds-txt"]),
        ):
            result = main()

        assert result == 0

    def test_analyze_with_failure(self):
        """Test analyze returns error on failure."""
        with (
            patch("src.cli.analyze_tlds_txt", return_value=1),
            patch.object(sys, "argv", ["cli", "--analyze", "tlds-txt"]),
        ):
            result = main()

        assert result == 1

    def test_analyze_invalid_file(self):
        """Test analyze with invalid file name."""
        with patch.object(sys, "argv", ["cli", "--analyze", "invalid-file"]):
            result = main()

        assert result == 1


class TestBuildCommand:
    """Tests for --build command."""

    def test_build_success(self):
        """Test build command succeeds."""
        mock_result = {
            "total_tlds": 1500,
            "output_file": "data/generated/tlds.json",
        }

        with (
            patch("src.cli.build_tlds_json", return_value=mock_result),
            patch.object(sys, "argv", ["cli", "--build"]),
        ):
            result = main()

        assert result == 0

    def test_build_with_error(self):
        """Test build returns error on failure."""
        mock_result = {"error": "Missing source file"}

        with (
            patch("src.cli.build_tlds_json", return_value=mock_result),
            patch.object(sys, "argv", ["cli", "--build"]),
        ):
            result = main()

        assert result == 1


class TestNoArguments:
    """Tests for CLI with no arguments."""

    def test_no_arguments_shows_help(self, capsys):
        """Test that no arguments prints help."""
        with patch.object(sys, "argv", ["cli"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or "IANA data ETL" in captured.out
