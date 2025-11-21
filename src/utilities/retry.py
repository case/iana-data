"""Retry utilities for handling transient errors."""

import logging

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_none,
)

logger = logging.getLogger(__name__)


class ServerError(Exception):
    """Raised when server returns 5xx error, triggering retry."""

    pass


def make_request_with_retry(
    client: httpx.Client,
    url: str,
    headers: dict[str, str] | None = None,
    max_attempts: int = 3,
    min_wait: int = 1,
    max_wait: int = 10,
) -> httpx.Response:
    """
    Make HTTP request with retry logic for transient errors.

    Retries on:
    - All network/transport errors (ConnectError, RemoteProtocolError, ReadError, etc.)
    - Server errors (5xx status codes)

    Does not retry on:
    - Client errors (4xx status codes)

    Args:
        client: httpx Client instance
        url: URL to request
        headers: Optional request headers
        max_attempts: Maximum number of attempts (default: 3)
        min_wait: Minimum wait between retries in seconds (default: 1)
        max_wait: Maximum wait between retries in seconds (default: 10)

    Returns:
        httpx Response object

    Raises:
        httpx.TransportError: After retries exhausted for network errors
        ServerError: After retries exhausted for 5xx errors
    """

    # Use no wait in tests (when min_wait=0) for speed
    if min_wait == 0:
        wait_strategy = wait_none()
        # Don't log retries in tests
        before_sleep_callback = None
    else:
        wait_strategy = wait_exponential(multiplier=1, min=min_wait, max=max_wait)
        # Log retry attempts at WARNING level
        before_sleep_callback = before_sleep_log(logger, logging.WARNING)

    @retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_strategy,
        retry=retry_if_exception_type((httpx.TransportError, ServerError)),
        before_sleep=before_sleep_callback,
        reraise=True,
    )
    def _request():
        response = client.get(url, headers=headers)
        # Raise ServerError for 5xx to trigger retry
        if 500 <= response.status_code < 600:
            raise ServerError(
                f"Server returned {response.status_code} for {url}"
            )
        return response

    return _request()
