#!/usr/bin/env python3
"""Tests for configuration."""

import os
from llmproxy.config import Settings


def _clear_llm_proxy_env():
    """Clear all LLM_PROXY environment variables."""
    for key in list(os.environ.keys()):
        if key.startswith("LLM_PROXY_"):
            del os.environ[key]


def test_default_values():
    """Test default configuration values."""
    _clear_llm_proxy_env()
    
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
    _clear_llm_proxy_env()
    
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
    _clear_llm_proxy_env()
    
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
    _clear_llm_proxy_env()
    
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
    _clear_llm_proxy_env()
    
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
    _clear_llm_proxy_env()
    
    settings = Settings()
    
    # Defaults
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.ollama_enable_compression == True
    
    # Override
    os.environ["LLM_PROXY_OLLAMA_BASE_URL"] = "http://ollama:11434"
    os.environ["LLM_PROXY_OLLAMA_MODEL"] = "mistral"
    
    try:
        settings = Settings()
        assert settings.ollama_base_url == "http://ollama:11434"
        assert settings.ollama_model == "mistral"
    finally:
        del os.environ["LLM_PROXY_OLLAMA_BASE_URL"]
        del os.environ["LLM_PROXY_OLLAMA_MODEL"]
    
    print("✓ Ollama settings work")


def test_filtering_settings():
    """Test message filtering settings."""
    _clear_llm_proxy_env()
    
    settings = Settings()
    
    # Defaults
    assert settings.deduplicate_system_messages == True
    assert settings.remove_empty_messages == True
    assert settings.strip_base64_images == False
    
    # Override
    os.environ["LLM_PROXY_DEDUPLICATE_SYSTEM_MESSAGES"] = "false"
    os.environ["LLM_PROXY_STRIP_BASE64_IMAGES"] = "true"
    
    try:
        settings = Settings()
        assert settings.deduplicate_system_messages == False
        assert settings.strip_base64_images == True
    finally:
        del os.environ["LLM_PROXY_DEDUPLICATE_SYSTEM_MESSAGES"]
        del os.environ["LLM_PROXY_STRIP_BASE64_IMAGES"]
    
    print("✓ Filtering settings work")


def test_type_coercion():
    """Test that string env vars are coerced to proper types."""
    _clear_llm_proxy_env()
    
    # Set values as strings (typical for env vars)
    os.environ["LLM_PROXY_PORT"] = "9000"
    os.environ["LLM_PROXY_ENABLE_CACHE"] = "false"
    os.environ["LLM_PROXY_CACHE_MAX_SIZE"] = "2000"
    os.environ["LLM_PROXY_RETRY_BACKOFF"] = "1.5"
    
    try:
        settings = Settings()
        assert settings.port == 9000  # int
        assert settings.enable_cache == False  # bool
        assert settings.cache_max_size == 2000  # int
        assert settings.retry_backoff == 1.5  # float
    finally:
        del os.environ["LLM_PROXY_PORT"]
        del os.environ["LLM_PROXY_ENABLE_CACHE"]
        del os.environ["LLM_PROXY_CACHE_MAX_SIZE"]
        del os.environ["LLM_PROXY_RETRY_BACKOFF"]
    
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
