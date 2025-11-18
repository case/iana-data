"""Tests for cache utilities."""

from datetime import datetime, timedelta, timezone

from src.utilities.cache import is_cache_fresh, parse_cache_control_max_age


def test_parse_cache_control_max_age_simple():
    """Test parsing simple max-age directive."""
    cache_control = "max-age=3600"
    result = parse_cache_control_max_age(cache_control)
    assert result == 3600


def test_parse_cache_control_max_age_with_other_directives():
    """Test parsing max-age with other directives."""
    cache_control = "public, max-age=21603, s-maxage=600"
    result = parse_cache_control_max_age(cache_control)
    assert result == 21603


def test_parse_cache_control_max_age_no_spaces():
    """Test parsing max-age without spaces."""
    cache_control = "public,max-age=26389"
    result = parse_cache_control_max_age(cache_control)
    assert result == 26389


def test_parse_cache_control_max_age_not_found():
    """Test parsing when max-age is not present."""
    cache_control = "public, no-cache"
    result = parse_cache_control_max_age(cache_control)
    assert result is None


def test_parse_cache_control_max_age_empty_string():
    """Test parsing empty cache control."""
    cache_control = ""
    result = parse_cache_control_max_age(cache_control)
    assert result is None


def test_is_cache_fresh_with_fresh_cache():
    """Test that recently downloaded file with max-age is considered fresh."""
    # Downloaded 1 hour ago, max-age is 6 hours
    download_time = datetime.now(timezone.utc) - timedelta(hours=1)

    metadata_entry = {
        "last_downloaded": download_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headers": {
            "cache_max_age": "21600",  # 6 hours
        },
    }

    assert is_cache_fresh(metadata_entry) is True


def test_is_cache_fresh_with_stale_cache():
    """Test that old downloaded file is considered stale."""
    # Downloaded 7 hours ago, max-age is 6 hours
    download_time = datetime.now(timezone.utc) - timedelta(hours=7)

    metadata_entry = {
        "last_downloaded": download_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headers": {
            "cache_max_age": "21600",  # 6 hours
        },
    }

    assert is_cache_fresh(metadata_entry) is False


def test_is_cache_fresh_missing_last_downloaded():
    """Test that missing last_downloaded returns False."""
    metadata_entry = {
        "headers": {
            "cache_max_age": "3600",
        },
    }

    assert is_cache_fresh(metadata_entry) is False


def test_is_cache_fresh_missing_headers():
    """Test that missing headers returns False."""
    metadata_entry = {
        "last_downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    assert is_cache_fresh(metadata_entry) is False


def test_is_cache_fresh_missing_cache_max_age():
    """Test that missing cache_max_age returns False."""
    metadata_entry = {
        "last_downloaded": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headers": {
            "etag": "abc123",
        },
    }

    assert is_cache_fresh(metadata_entry) is False


def test_is_cache_fresh_boundary_condition():
    """Test cache freshness at exact max-age boundary."""
    # Downloaded exactly max-age seconds ago
    max_age = 3600
    download_time = datetime.now(timezone.utc) - timedelta(seconds=max_age)

    metadata_entry = {
        "last_downloaded": download_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headers": {
            "cache_max_age": str(max_age),
        },
    }

    # Should be stale (age == max_age, not less than)
    assert is_cache_fresh(metadata_entry) is False


def test_is_cache_fresh_short_max_age():
    """Test with very short max-age like tlds.txt (205 seconds)."""
    # Downloaded yesterday, max-age is 205 seconds (definitely stale)
    download_time = datetime.now(timezone.utc) - timedelta(days=1)

    metadata_entry = {
        "last_downloaded": download_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headers": {
            "cache_max_age": "205",
        },
    }

    assert is_cache_fresh(metadata_entry) is False
