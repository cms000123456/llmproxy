#!/usr/bin/env python3
"""Tests for PII sanitization middleware."""

import json
from llmproxy.middleware.sanitize import (
    SanitizationMiddleware,
    sanitize_for_logging,
    sanitize_dict_for_logging,
)


def test_api_key_redaction():
    """Test OpenAI-style API key redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = "My API key is sk-abcdefghijklmnopqrstuvwxyz12345678901234567890abcd"
    result = middleware._sanitize_string(text)
    
    assert "[API_KEY_REDACTED]" in result
    assert "sk-" not in result or "[API_KEY_REDACTED]" in result
    print("✓ API key redaction works")


def test_bearer_token_redaction():
    """Test Bearer token redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9'
    result = middleware._sanitize_string(text)
    
    assert "[TOKEN_REDACTED]" in result
    print("✓ Bearer token redaction works")


def test_credit_card_redaction():
    """Test credit card number redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    cards = [
        "4532015112830366",  # Visa
        "5425233430109903",  # Mastercard
        "374245455400126",   # Amex
    ]
    
    for card in cards:
        result = middleware._sanitize_string(f"My card is {card}")
        assert "[CREDIT_CARD_REDACTED]" in result
    
    print("✓ Credit card redaction works")


def test_email_redaction():
    """Test email address redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = "Contact me at user@example.com or admin@company.org"
    result = middleware._sanitize_string(text)
    
    assert result.count("[EMAIL_REDACTED]") == 2
    assert "user@example.com" not in result
    print("✓ Email redaction works")


def test_phone_redaction():
    """Test phone number redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    phones = [
        "555-123-4567",
        "(555) 123-4567",
        "555.123.4567",
        "5551234567",
    ]
    
    for phone in phones:
        result = middleware._sanitize_string(f"Call me at {phone}")
        assert "[PHONE_REDACTED]" in result
    
    print("✓ Phone number redaction works")


def test_ssn_redaction():
    """Test SSN redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = "My SSN is 123-45-6789"
    result = middleware._sanitize_string(text)
    
    assert "[SSN_REDACTED]" in result
    assert "123-45-6789" not in result
    print("✓ SSN redaction works")


def test_private_key_redaction():
    """Test SSH private key redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    key = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
-----END OPENSSH PRIVATE KEY-----"""
    
    result = middleware._sanitize_string(key)
    assert "[PRIVATE_KEY_REDACTED]" in result
    print("✓ Private key redaction works")


def test_password_in_json_redaction():
    """Test password field redaction in JSON strings."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    # Test with actual JSON string (with quotes)
    text = '{"username": "admin", "password": "secret123"}'
    result = middleware._sanitize_string(text)
    
    assert "[PASSWORD_REDACTED]" in result
    assert "secret123" not in result
    print("✓ Password field redaction works")


def test_aws_key_redaction():
    """Test AWS access key redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = "AWS Access Key: AKIAIOSFODNN7EXAMPLE"
    result = middleware._sanitize_string(text)
    
    assert "[AWS_KEY_REDACTED]" in result
    print("✓ AWS key redaction works")


def test_github_token_redaction():
    """Test GitHub token redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    text = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    result = middleware._sanitize_string(text)
    
    assert "[GITHUB_TOKEN_REDACTED]" in result
    print("✓ GitHub token redaction works")


def test_slack_token_redaction():
    """Test Slack token redaction."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    # Construct token dynamically to avoid secret scanning false positives
    prefix = "xox" + "b"
    fake_token = f"{prefix}-TESTTESTTEST-TESTTESTTEST-TESTTESTTESTTEST"
    text = f"Error: {fake_token} is invalid"
    result = middleware._sanitize_string(text)
    
    assert "[SLACK_TOKEN_REDACTED]" in result
    print("✓ Slack token redaction works")


def test_nested_dict_sanitization():
    """Test sanitization of nested dictionaries."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    # When sanitizing a dict, values don't have JSON quotes
    # The middleware processes the actual values
    data = {
        "user": {
            "email": "user@example.com",  # Will be redacted
            "name": "John",  # Will NOT be redacted
        },
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz12345678901234567890abcd",
        "messages": [
            {"content": "Call me at 555-123-4567"},
            {"content": "My card is 4532015112830366"}
        ]
    }
    
    result = middleware._sanitize_object(data)
    
    assert result["user"]["email"] == "[EMAIL_REDACTED]"
    assert result["user"]["name"] == "John"  # Unchanged
    assert "[API_KEY_REDACTED]" in result["api_key"]
    assert "[PHONE_REDACTED]" in result["messages"][0]["content"]
    assert "[CREDIT_CARD_REDACTED]" in result["messages"][1]["content"]
    print("✓ Nested dict sanitization works")


def test_list_sanitization():
    """Test sanitization of lists."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    data = [
        "user@example.com",
        "555-123-4567",
        {"token": "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}
    ]
    
    result = middleware._sanitize_object(data)
    
    assert result[0] == "[EMAIL_REDACTED]"
    assert result[1] == "[PHONE_REDACTED]"
    assert "[GITHUB_TOKEN_REDACTED]" in result[2]["token"]
    print("✓ List sanitization works")


def test_sanitization_disabled():
    """Test that middleware sanitization can be disabled."""
    # Create middleware with enabled=False
    middleware_disabled = SanitizationMiddleware(None, enabled=False)
    
    text = "sk-abcdefghijklmnopqrstuvwxyz12345678901234567890abcd"
    result = middleware_disabled._sanitize_string(text)
    
    # Should NOT be redacted when disabled
    assert "sk-" in result
    assert "[API_KEY_REDACTED]" not in result
    print("✓ Middleware sanitization disable works")


def test_standalone_sanitize_for_logging():
    """Test standalone sanitize_for_logging function (always sanitizes)."""
    # Note: The standalone function always sanitizes (for logging safety)
    text = "sk-abcdefghijklmnopqrstuvwxyz12345678901234567890abcd user@example.com"
    result = sanitize_for_logging(text)
    
    assert "[API_KEY_REDACTED]" in result
    assert "[EMAIL_REDACTED]" in result
    print("✓ Standalone sanitize_for_logging works (always on)")


def test_standalone_sanitize_dict_for_logging():
    """Test standalone sanitize_dict_for_logging function."""
    data = {
        "api_key": "sk-abcdefghijklmnopqrstuvwxyz12345678901234567890abcd",
        "user": "admin"
    }
    result = sanitize_dict_for_logging(data)
    
    assert "[API_KEY_REDACTED]" in result["api_key"]
    assert result["user"] == "admin"  # Unchanged
    print("✓ Standalone sanitize_dict_for_logging works")


def test_no_false_positives():
    """Test that normal text is not incorrectly redacted."""
    middleware = SanitizationMiddleware(None, enabled=True)
    
    normal_texts = [
        "Hello world",
        "The quick brown fox jumps over 13 lazy dogs",
        "Version 1.2.3",
        "Meeting at 3:00 PM",
        "Price: $123.45",
    ]
    
    for text in normal_texts:
        result = middleware._sanitize_string(text)
        # Should not contain any redaction markers
        assert "REDACTED" not in result, f"False positive: {text}"
    
    print("✓ No false positives on normal text")


if __name__ == "__main__":
    test_api_key_redaction()
    test_bearer_token_redaction()
    test_credit_card_redaction()
    test_email_redaction()
    test_phone_redaction()
    test_ssn_redaction()
    test_private_key_redaction()
    test_password_in_json_redaction()
    test_aws_key_redaction()
    test_github_token_redaction()
    test_slack_token_redaction()
    test_nested_dict_sanitization()
    test_list_sanitization()
    test_sanitization_disabled()
    test_standalone_sanitize_for_logging()
    test_standalone_sanitize_dict_for_logging()
    test_no_false_positives()
    print("\n✅ All sanitization tests passed!")
