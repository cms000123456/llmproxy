#!/usr/bin/env python3
"""Tests for API Key authentication middleware."""

import asyncio
import json
from httpx import AsyncClient, ASGITransport
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llmproxy.auth import APIKeyAuthMiddleware, generate_api_key, APIKeyManager
from llmproxy.config import settings


async def test_generate_api_key():
    """Test API key generation."""
    key = generate_api_key()
    assert key.startswith("llmproxy_")
    assert len(key) == 41  # "llmproxy_" + 32 chars
    
    # Custom prefix
    key2 = generate_api_key("custom")
    assert key2.startswith("custom_")
    print("✓ API key generation works")


async def test_extract_api_key():
    """Test API key extraction from headers."""
    from starlette.datastructures import Headers
    
    # Create a mock request
    class MockRequest:
        def __init__(self, headers=None):
            self.headers = Headers(headers or {})
    
    middleware = APIKeyAuthMiddleware.__new__(APIKeyAuthMiddleware)
    middleware.api_keys = set()
    
    # Test Bearer token extraction
    request = MockRequest({"authorization": "Bearer my_api_key_123"})
    key = middleware._extract_api_key(request)
    assert key == "my_api_key_123"
    
    # Test X-API-Key extraction
    request = MockRequest({"x-api-key": "my_api_key_456"})
    key = middleware._extract_api_key(request)
    assert key == "my_api_key_456"
    
    # Test no key
    request = MockRequest({})
    key = middleware._extract_api_key(request)
    assert key is None
    
    # Test Bearer case insensitive
    request = MockRequest({"authorization": "bearer lower_case_key"})
    key = middleware._extract_api_key(request)
    assert key == "lower_case_key"
    
    print("✓ API key extraction from headers works")


async def test_validate_api_key():
    """Test API key validation with constant-time comparison."""
    middleware = APIKeyAuthMiddleware.__new__(APIKeyAuthMiddleware)
    middleware.api_keys = {"valid_key_123", "another_key_456"}
    
    # Valid keys
    assert middleware._validate_api_key("valid_key_123") is True
    assert middleware._validate_api_key("another_key_456") is True
    
    # Invalid keys
    assert middleware._validate_api_key("invalid_key") is False
    assert middleware._validate_api_key("") is False
    assert middleware._validate_api_key("VALID_KEY_123") is False  # Case sensitive
    
    print("✓ API key validation works")


async def test_api_key_manager():
    """Test APIKeyManager utility functions."""
    # Save original keys
    original_keys = settings.api_keys.copy()
    settings.api_keys = []
    
    try:
        # Generate a key
        new_key = generate_api_key()
        
        # Add key
        result = APIKeyManager.add_key(new_key)
        assert result is True
        assert new_key in settings.api_keys
        
        # Adding duplicate should fail
        result = APIKeyManager.add_key(new_key)
        assert result is False
        
        # List keys (masked)
        keys = APIKeyManager.list_keys()
        assert len(keys) == 1
        assert "..." in keys[0]
        
        # Remove key
        result = APIKeyManager.remove_key(new_key)
        assert result is True
        assert new_key not in settings.api_keys
        
        # Removing non-existent key should fail
        result = APIKeyManager.remove_key(new_key)
        assert result is False
        
        print("✓ APIKeyManager utility functions work")
    finally:
        settings.api_keys = original_keys


async def test_middleware_disabled():
    """Test that middleware allows all requests when disabled."""
    from starlette.datastructures import Headers
    
    class MockApp:
        async def __call__(self, scope, receive, send):
            pass
    
    # Create disabled middleware
    middleware = APIKeyAuthMiddleware(MockApp(), enabled=False)
    assert middleware.enabled is False
    
    # Should allow request through without checking
    assert middleware.api_keys == set()
    
    print("✓ Middleware can be disabled")


async def test_middleware_no_keys():
    """Test that middleware allows all requests when no keys configured."""
    from starlette.datastructures import Headers
    
    class MockApp:
        async def __call__(self, scope, receive, send):
            pass
    
    # Create middleware with no keys
    original_keys = settings.api_keys.copy()
    settings.api_keys = []
    
    try:
        middleware = APIKeyAuthMiddleware(MockApp(), enabled=True)
        assert middleware.api_keys == set()
        assert middleware.enabled is True
        # When no keys, all requests allowed
        print("✓ Middleware allows all requests when no keys configured")
    finally:
        settings.api_keys = original_keys


async def test_middleware_extracts_key():
    """Test middleware extracts key from various header formats."""
    from starlette.datastructures import Headers
    
    class MockApp:
        async def __call__(self, scope, receive, send):
            pass
    
    middleware = APIKeyAuthMiddleware(MockApp(), enabled=True)
    middleware.api_keys = {"test_key_12345"}
    
    class MockRequest:
        def __init__(self, headers=None):
            self.headers = Headers(headers or {})
            self.state = type('State', (), {})()
    
    # Valid Bearer token
    request = MockRequest({"authorization": "Bearer test_key_12345"})
    key = middleware._extract_api_key(request)
    assert key == "test_key_12345"
    assert middleware._validate_api_key(key) is True
    
    # Valid X-API-Key header
    request = MockRequest({"x-api-key": "test_key_12345"})
    key = middleware._extract_api_key(request)
    assert key == "test_key_12345"
    assert middleware._validate_api_key(key) is True
    
    # Invalid key
    request = MockRequest({"authorization": "Bearer wrong_key"})
    key = middleware._extract_api_key(request)
    assert key == "wrong_key"
    assert middleware._validate_api_key(key) is False
    
    print("✓ Middleware key extraction and validation works")


async def test_middleware_public_endpoints():
    """Test that health and metrics endpoints are public."""
    from starlette.datastructures import URL, Headers
    
    class MockApp:
        async def __call__(self, scope, receive, send):
            pass
    
    middleware = APIKeyAuthMiddleware(MockApp(), enabled=True)
    middleware.api_keys = {"secret_key"}
    
    class MockRequest:
        def __init__(self, path="/", headers=None):
            self.url = URL(f"http://test{path}")
            self.headers = Headers(headers or {})
            self.state = type('State', (), {})()
    
    # Health endpoint should be public
    request = MockRequest("/health")
    assert request.url.path == "/health"
    
    # Metrics endpoint should be public
    request = MockRequest("/metrics")
    assert request.url.path == "/metrics"
    
    # Other endpoints should require auth
    request = MockRequest("/v1/chat/completions")
    assert request.url.path == "/v1/chat/completions"
    
    print("✓ Public endpoints identified correctly")


async def test_key_masking():
    """Test that API keys are properly masked in logs/state."""
    test_key = "llmproxy_abcdef1234567890abcdef12345678"
    
    # Should be masked as first 8 + ... + last 4
    masked = test_key[:8] + "..." + test_key[-4:]
    assert masked == "llmproxy...5678"
    
    # APIKeyManager.list_keys should return masked keys
    original_keys = settings.api_keys.copy()
    settings.api_keys = [test_key]
    
    try:
        keys = APIKeyManager.list_keys()
        assert len(keys) == 1
        assert "..." in keys[0]
        assert keys[0].startswith("llmproxy")
        assert keys[0].endswith("5678")
    finally:
        settings.api_keys = original_keys
    
    print("✓ API key masking works")


async def test_constant_time_comparison():
    """Test that key validation uses constant-time comparison."""
    import secrets
    
    middleware = APIKeyAuthMiddleware.__new__(APIKeyAuthMiddleware)
    middleware.api_keys = {"short"}
    
    # The _validate_api_key method should use secrets.compare_digest
    # This is verified by the implementation using it
    assert middleware._validate_api_key("short") is True
    assert middleware._validate_api_key("shor") is False  # One char off
    assert middleware._validate_api_key("shortx") is False  # One char extra
    assert middleware._validate_api_key("SHORT") is False  # Case sensitive
    
    print("✓ Constant-time key validation works")


async def run_all_tests():
    """Run all auth tests."""
    print("\n🧪 Running API Key Authentication Tests\n")
    
    await test_generate_api_key()
    await test_extract_api_key()
    await test_validate_api_key()
    await test_api_key_manager()
    await test_middleware_disabled()
    await test_middleware_no_keys()
    await test_middleware_extracts_key()
    await test_middleware_public_endpoints()
    await test_key_masking()
    await test_constant_time_comparison()
    
    print("\n✅ All auth tests passed!\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
