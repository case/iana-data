"""Tests for CLI module."""

import sys
from unittest.mock import patch

import pytest

from src.cli import EXIT_FETCH_FAILED, EXIT_PAYLOAD_REJECTED, main


class TestDownloadCommand:
    """Tests for --download command."""

    def test_download_all_sources_success(self):
        """Test downloading all sources successfully."""
        mock_results = {
            "RDAP_BOOTSTRAP": "downloaded",
            "TLD_LIST": "not_modified",
            "IANA_TLDS": "downloaded",
        }

        with (
            patch("src.cli.download_iana_files", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download"]),
        ):
            result = main()

        assert result == 0

    def test_download_specific_source_success(self):
        """Test downloading a specific source."""
        mock_results = {"TLD_LIST": "downloaded"}

        with (
            patch("src.cli.download_iana_files", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download", "TLD_LIST"]),
        ):
            result = main()

        assert result == 0

    def test_download_with_error(self):
        """Test download returns error code on failure."""
        mock_results = {
            "RDAP_BOOTSTRAP": "downloaded",
            "TLD_LIST": "error",
            "IANA_TLDS": "downloaded",
        }

        with (
            patch("src.cli.download_iana_files", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download"]),
        ):
            result = main()

        assert result == EXIT_FETCH_FAILED == 3

    def test_download_crash_is_not_mistaken_for_a_failed_fetch(self):
        """An uncaught exception exits 1 in Python, so it must not share a code."""
        with (
            patch("src.cli.download_iana_files", side_effect=RuntimeError("boom")),
            patch.object(sys, "argv", ["cli", "--download"]),
            pytest.raises(RuntimeError, match="boom"),
        ):
            main()

        assert 1 not in {EXIT_FETCH_FAILED, EXIT_PAYLOAD_REJECTED}
        assert 2 not in {EXIT_FETCH_FAILED, EXIT_PAYLOAD_REJECTED}

    def test_download_with_invalid_payload_has_its_own_exit_code(self):
        """A rejected payload has its own exit code, so the nightly can alert on it."""
        mock_results = {
            "RDAP_BOOTSTRAP": "downloaded",
            "TLD_LIST": "not_modified",
            "IANA_TLDS": "invalid",
        }

        with (
            patch("src.cli.download_iana_files", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download"]),
        ):
            result = main()

        assert result == EXIT_PAYLOAD_REJECTED == 4

    def test_download_invalid_payload_outranks_a_fetch_error(self):
        mock_results = {
            "RDAP_BOOTSTRAP": "error",
            "TLD_LIST": "not_modified",
            "IANA_TLDS": "invalid",
        }

        with (
            patch("src.cli.download_iana_files", return_value=mock_results),
            patch.object(sys, "argv", ["cli", "--download"]),
        ):
            result = main()

        assert result == EXIT_PAYLOAD_REJECTED == 4

    def test_download_tld_pages_flag_is_gone(self):
        with (
            patch.object(sys, "argv", ["cli", "--download-tld-pages"]),
            pytest.raises(SystemExit) as excinfo,
        ):
            main()

        assert excinfo.value.code == 2

    def test_download_invalid_source(self):
        """Test download with invalid source name."""
        with patch.object(sys, "argv", ["cli", "--download", "INVALID_SOURCE"]):
            result = main()

        assert result == 1


class TestAnalyzeCommand:
    """Tests for --analyze command."""

    def test_analyze_all_files_success(self):
        """Test analyzing all files successfully."""
        with (
            patch("src.cli.analyze_tlds_txt", return_value=0),
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
