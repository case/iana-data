"""Tests for retry utilities."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.utilities.retry import ServerError, make_request_with_retry


def test_make_request_with_retry_success():
    """Test successful request without retry."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_client.get.return_value = mock_response

    response = make_request_with_retry(
        client=mock_client, url="http://example.com", min_wait=0
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 1


def test_make_request_with_retry_server_error_then_success():
    """Test retry on server error (5xx) then success."""
    mock_client = MagicMock(spec=httpx.Client)

    # First call: 500 error, second call: success
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 500

    mock_success_response = MagicMock(spec=httpx.Response)
    mock_success_response.status_code = 200

    mock_client.get.side_effect = [mock_error_response, mock_success_response]

    response = make_request_with_retry(
        client=mock_client, url="http://example.com", min_wait=0, max_attempts=2
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 2


def test_make_request_with_retry_server_error_exhausted():
    """Test retry exhaustion on persistent server error."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 503
    mock_client.get.return_value = mock_error_response

    with pytest.raises(ServerError, match="Server returned 503"):
        make_request_with_retry(
            client=mock_client, url="http://example.com", min_wait=0, max_attempts=2
        )

    assert mock_client.get.call_count == 2


def test_make_request_with_retry_transport_error_then_success():
    """Test retry on transport error then success."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_success_response = MagicMock(spec=httpx.Response)
    mock_success_response.status_code = 200

    # First call: transport error, second call: success
    mock_client.get.side_effect = [
        httpx.ConnectError("Connection failed"),
        mock_success_response,
    ]

    response = make_request_with_retry(
        client=mock_client, url="http://example.com", min_wait=0, max_attempts=2
    )

    assert response.status_code == 200
    assert mock_client.get.call_count == 2


def test_make_request_with_retry_transport_error_exhausted():
    """Test retry exhaustion on persistent transport error."""
    mock_client = MagicMock(spec=httpx.Client)
    mock_client.get.side_effect = httpx.ReadTimeout("Timeout")

    with pytest.raises(httpx.ReadTimeout):
        make_request_with_retry(
            client=mock_client, url="http://example.com", min_wait=0, max_attempts=2
        )

    assert mock_client.get.call_count == 2


def test_make_request_with_retry_no_retry_on_client_error():
    """Test that 4xx errors do not trigger retry."""
    mock_client = MagicMock(spec=httpx.Client)

    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 404
    mock_client.get.return_value = mock_error_response

    response = make_request_with_retry(
        client=mock_client, url="http://example.com", min_wait=0
    )

    # Should not retry on 4xx
    assert response.status_code == 404
    assert mock_client.get.call_count == 1


def test_make_request_with_retry_production_path_with_logging():
    """Test production retry path with exponential backoff and logging."""
    mock_client = MagicMock(spec=httpx.Client)

    # First call: 500 error, second call: success
    mock_error_response = MagicMock(spec=httpx.Response)
    mock_error_response.status_code = 502

    mock_success_response = MagicMock(spec=httpx.Response)
    mock_success_response.status_code = 200

    mock_client.get.side_effect = [mock_error_response, mock_success_response]

    # Use production retry settings (min_wait > 0) to exercise lines 64-66
    # Mock sleep to avoid actual delays
    with patch("tenacity.nap.sleep"):
        response = make_request_with_retry(
            client=mock_client,
            url="http://example.com",
            min_wait=1,  # Production setting (not 0)
            max_wait=10,
            max_attempts=2,
        )

    assert response.status_code == 200
    assert mock_client.get.call_count == 2
