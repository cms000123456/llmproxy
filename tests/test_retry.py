#!/usr/bin/env python3
"""Tests for retry logic with exponential backoff."""

import asyncio
import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llmproxy.server import (
    _calculate_backoff,
    _upstream_request_with_retry,
)


def test_calculate_backoff_basic():
    """Test exponential backoff calculation."""
    # Attempt 0: base * 2^0 = base
    wait = _calculate_backoff(attempt=0, base=2.0, max_wait=60.0)
    assert 1.5 <= wait <= 2.5  # 2.0 ± 25% jitter

    # Attempt 1: base * 2^1 = 4.0
    wait = _calculate_backoff(attempt=1, base=2.0, max_wait=60.0)
    assert 3.0 <= wait <= 5.0  # 4.0 ± 25% jitter

    # Attempt 2: base * 2^2 = 8.0
    wait = _calculate_backoff(attempt=2, base=2.0, max_wait=60.0)
    assert 6.0 <= wait <= 10.0  # 8.0 ± 25% jitter
    print("✓ Backoff calculation works with exponential growth")


def test_calculate_backoff_max_wait():
    """Test that backoff respects max_wait cap."""
    # With high attempt, should still cap at max_wait
    wait = _calculate_backoff(attempt=10, base=2.0, max_wait=10.0)
    assert wait <= 10.0
    print("✓ Backoff respects max_wait cap")


def test_calculate_backoff_jitter():
    """Test that jitter introduces variation."""
    waits = [_calculate_backoff(attempt=2, base=2.0, max_wait=60.0) for _ in range(100)]
    # All waits should be different (very unlikely to be identical with jitter)
    assert len(set(waits)) > 50, "Jitter should produce varied results"
    print("✓ Jitter produces varied backoff times")


@pytest.mark.asyncio
async def test_retry_on_timeout():
    """Test retry on timeout exception."""
    mock_client = MagicMock()
    
    # First 2 calls timeout, 3rd succeeds
    mock_client.request = AsyncMock(side_effect=[
        httpx.TimeoutException("Timeout"),
        httpx.TimeoutException("Timeout"),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,  # Fast for testing
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 3
    assert mock_sleep.call_count == 2  # Slept between retries
    print("✓ Retry on timeout works")


@pytest.mark.asyncio
async def test_retry_on_connect_error():
    """Test retry on connection error."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        httpx.ConnectError("Connection refused"),
        httpx.ConnectError("Connection refused"),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 3
    print("✓ Retry on connection error works")


@pytest.mark.asyncio
async def test_retry_on_server_error():
    """Test retry on 5xx server errors."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        MagicMock(status_code=502, headers={}, content=b'{"error": "bad gateway"}'),
        MagicMock(status_code=503, headers={}, content=b'{"error": "service unavailable"}'),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 3
    print("✓ Retry on 5xx server errors works")


@pytest.mark.asyncio
async def test_retry_on_rate_limit_with_header():
    """Test retry on 429 with Retry-After header."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        MagicMock(status_code=429, headers={"retry-after": "1"}, content=b'{"error": "rate limited"}'),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 2
    # Should have used the Retry-After header value
    mock_sleep.assert_called_once()
    print("✓ Retry on 429 with Retry-After header works")


@pytest.mark.asyncio
async def test_retry_on_rate_limit_without_header():
    """Test retry on 429 without Retry-After header uses exponential backoff."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        MagicMock(status_code=429, headers={}, content=b'{"error": "rate limited"}'),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 2
    mock_sleep.assert_called_once()
    print("✓ Retry on 429 without Retry-After header uses backoff")


@pytest.mark.asyncio
async def test_no_retry_on_4xx_errors():
    """Test that 4xx errors (except 429) are not retried."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(return_value=MagicMock(
        status_code=400, 
        headers={}, 
        content=b'{"error": "bad request"}'
    ))

    response = await _upstream_request_with_retry(
        http_client=mock_client,
        method="POST",
        url="/v1/chat/completions",
        headers={},
        json_payload={"messages": []},
        content=None,
        max_retries=3,
        backoff_base=0.1,
        max_wait=1.0
    )

    assert response.status_code == 400
    assert mock_client.request.call_count == 1  # No retry
    print("✓ No retry on 4xx errors (except 429)")


@pytest.mark.asyncio
async def test_max_retries_exhausted_timeout():
    """Test that exception is raised when max retries exhausted (timeout)."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        httpx.TimeoutException("Timeout"),
        httpx.TimeoutException("Timeout"),
        httpx.TimeoutException("Timeout"),
        httpx.TimeoutException("Timeout"),
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock):
        try:
            await _upstream_request_with_retry(
                http_client=mock_client,
                method="POST",
                url="/v1/chat/completions",
                headers={},
                json_payload={"messages": []},
                content=None,
                max_retries=3,  # 3 retries + 1 initial = 4 total
                backoff_base=0.01,
                max_wait=0.1
            )
            assert False, "Should have raised TimeoutException"
        except httpx.TimeoutException:
            pass

    assert mock_client.request.call_count == 4
    print("✓ Exception raised when max retries exhausted (timeout)")


@pytest.mark.asyncio
async def test_max_retries_exhausted_server_error():
    """Test that response is returned when max retries exhausted (5xx)."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        MagicMock(status_code=503, headers={}, content=b'{"error": "unavailable"}'),
        MagicMock(status_code=503, headers={}, content=b'{"error": "unavailable"}'),
        MagicMock(status_code=503, headers={}, content=b'{"error": "unavailable"}'),
        MagicMock(status_code=503, headers={}, content=b'{"error": "unavailable"}'),
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock):
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.01,
            max_wait=0.1
        )

    assert response.status_code == 503
    assert mock_client.request.call_count == 4
    print("✓ Response returned when max retries exhausted (5xx)")


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    """Test successful request on first attempt (no retries)."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(return_value=MagicMock(
        status_code=200, 
        headers={}, 
        content=b'{"choices": [{"message": {"content": "Hello"}}]}'
    ))

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": [{"role": "user", "content": "Hi"}]},
            content=None,
            max_retries=3,
            backoff_base=2.0,
            max_wait=60.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 1
    mock_sleep.assert_not_called()  # No sleeps on success
    print("✓ Success on first attempt (no retries)")


@pytest.mark.asyncio
async def test_network_error_retry():
    """Test retry on network errors."""
    mock_client = MagicMock()
    
    mock_client.request = AsyncMock(side_effect=[
        httpx.NetworkError("Network unreachable"),
        MagicMock(status_code=200, headers={}, content=b'{"ok": true}')
    ])

    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        response = await _upstream_request_with_retry(
            http_client=mock_client,
            method="POST",
            url="/v1/chat/completions",
            headers={},
            json_payload={"messages": []},
            content=None,
            max_retries=3,
            backoff_base=0.1,
            max_wait=1.0
        )

    assert response.status_code == 200
    assert mock_client.request.call_count == 2
    print("✓ Retry on network error works")


async def run_all_tests():
    """Run all retry tests."""
    print("\n🧪 Running Retry Logic Tests\n")
    
    # Sync tests
    test_calculate_backoff_basic()
    test_calculate_backoff_max_wait()
    test_calculate_backoff_jitter()
    
    # Async tests
    await test_retry_on_timeout()
    await test_retry_on_connect_error()
    await test_retry_on_server_error()
    await test_retry_on_rate_limit_with_header()
    await test_retry_on_rate_limit_without_header()
    await test_no_retry_on_4xx_errors()
    await test_max_retries_exhausted_timeout()
    await test_max_retries_exhausted_server_error()
    await test_success_on_first_attempt()
    await test_network_error_retry()
    
    print("\n✅ All retry tests passed!\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
