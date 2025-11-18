"""Shared pytest fixtures and configuration."""

from unittest.mock import patch

import pytest

from src.utilities.retry import make_request_with_retry as original_make_request


@pytest.fixture(autouse=True)
def fast_retries():
    """Disable retry wait times in all tests for speed."""

    def fast_request(client, url, headers=None, max_attempts=3, min_wait=1, max_wait=10):
        # Always use min_wait=0 in tests to skip delays
        return original_make_request(
            client, url, headers=headers, max_attempts=max_attempts, min_wait=0, max_wait=0
        )

    with patch("src.utilities.download.make_request_with_retry", fast_request):
        yield
