#!/usr/bin/env python3
"""Tests for configuration."""

import os
from llmproxy.config import Settings


def test_default_values():
    """Test default configuration values."""
    settings = Settings()
    
    assert settings.upstream_base_url == "https://api.moonshot.cn/v1"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.enable_filtering == True
    assert settings.enable_compression == True
    assert settings.enable_cache == True
    assert settings.max_message_length == 32000
    assert settings.max_total_tokens == 120000
    print("✓ Default values correct")


def test_env_prefix():
    """Test that environment variables with prefix are loaded."""
    # Set some env vars
    os.environ["LLM_PROXY_PORT"] = "9999"
    os.environ["LLM_PROXY_LOG_LEVEL"] = "DEBUG"
    
    try:
        settings = Settings()
        assert settings.port == 9999
        assert settings.log_level == "DEBUG"
    finally:
        # Clean up
        del os.environ["LLM_PROXY_PORT"]
        del os.environ["LLM_PROXY_LOG_LEVEL"]
    
    print("✓ Environment variable loading works")


def test_env_override():
    """Test that env vars override defaults."""
    os.environ["LLM_PROXY_ENABLE_CACHE"] = "false"
    os.environ["LLM_PROXY_CACHE_MAX_SIZE"] = "500"
    
    try:
        settings = Settings()
        assert settings.enable_cache == False
        assert settings.cache_max_size == 500
    finally:
        del os.environ["LLM_PROXY_ENABLE_CACHE"]
        del os.environ["LLM_PROXY_CACHE_MAX_SIZE"]
    
    print("✓ Environment override works")


def test_compression_strategies():
    """Test valid compression strategies."""
    settings = Settings()
    
    # Default should be truncate_oldest
    assert settings.compression_strategy == "truncate_oldest"
    
    # Can be set to summarize_oldest
    os.environ["LLM_PROXY_COMPRESSION_STRATEGY"] = "summarize_oldest"
    try:
        settings = Settings()
        assert settings.compression_strategy == "summarize_oldest"
    finally:
        del os.environ["LLM_PROXY_COMPRESSION_STRATEGY"]
    
    print("✓ Compression strategies work")


def test_kimi_code_compat():
    """Test Kimi Code compatibility settings."""
    settings = Settings()
    
    # Defaults
    assert settings.kimi_code_compat == False
    assert settings.kimi_code_version == "1.0.0"
    assert settings.kimi_code_device_name == "kimi-proxy"
    
    # Override
    os.environ["LLM_PROXY_KIMI_CODE_COMPAT"] = "true"
    os.environ["LLM_PROXY_KIMI_CODE_VERSION"] = "2.0.0"
    
    try:
        settings = Settings()
        assert settings.kimi_code_compat == True
        assert settings.kimi_code_version == "2.0.0"
    finally:
        del os.environ["LLM_PROXY_KIMI_CODE_COMPAT"]
        del os.environ["LLM_PROXY_KIMI_CODE_VERSION"]
    
    print("✓ Kimi Code settings work")


def test_ollama_settings():
    """Test Ollama integration settings."""
    settings = Settings()
    
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.ollama_enable_compression == True
    assert settings.ollama_relevance_threshold == 0.5
    print("✓ Ollama settings correct")


def test_filtering_settings():
    """Test filtering configuration."""
    settings = Settings()
    
    assert settings.deduplicate_system_messages == True
    assert settings.remove_empty_messages == True
    assert settings.strip_base64_images == False
    print("✓ Filtering settings correct")


def test_type_coercion():
    """Test type coercion from environment variables."""
    # Env vars are strings, should be coerced to proper types
    os.environ["LLM_PROXY_PORT"] = "9090"
    os.environ["LLM_PROXY_ENABLE_CACHE"] = "false"
    os.environ["LLM_PROXY_OLLAMA_RELEVANCE_THRESHOLD"] = "0.75"
    
    try:
        settings = Settings()
        assert isinstance(settings.port, int)
        assert isinstance(settings.enable_cache, bool)
        assert isinstance(settings.ollama_relevance_threshold, float)
        assert settings.ollama_relevance_threshold == 0.75
    finally:
        del os.environ["LLM_PROXY_PORT"]
        del os.environ["LLM_PROXY_ENABLE_CACHE"]
        del os.environ["LLM_PROXY_OLLAMA_RELEVANCE_THRESHOLD"]
    
    print("✓ Type coercion works")


if __name__ == "__main__":
    test_default_values()
    test_env_prefix()
    test_env_override()
    test_compression_strategies()
    test_kimi_code_compat()
    test_ollama_settings()
    test_filtering_settings()
    test_type_coercion()
    print("\n✅ All config tests passed!")
