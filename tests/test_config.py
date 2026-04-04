#!/usr/bin/env python3
"""Tests for configuration."""

import os


def _clear_llm_proxy_env():
    """Clear all LLM_PROXY environment variables."""
    for key in list(os.environ.keys()):
        if key.startswith("LLM_PROXY_"):
            del os.environ[key]


def _get_settings_without_env_file():
    """Get settings without loading .env file (for testing true defaults)."""
    _clear_llm_proxy_env()
    # Temporarily rename .env to prevent loading
    env_path = ".env"
    env_backup = ".env.backup"
    env_existed = os.path.exists(env_path)

    if env_existed:
        os.rename(env_path, env_backup)

    try:
        # Force reimport to get fresh settings
        import importlib

        from llmproxy import config

        importlib.reload(config)
        return config.Settings()
    finally:
        if env_existed:
            os.rename(env_backup, env_path)


def test_default_values():
    """Test default configuration values."""
    settings = _get_settings_without_env_file()

    assert settings.upstream_base_url == "https://api.moonshot.cn/v1"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8080
    assert settings.enable_filtering 
    assert settings.enable_compression 
    assert settings.enable_cache 
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
        # Force reimport to pick up env vars
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
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
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.enable_cache 
        assert settings.cache_max_size == 500
    finally:
        del os.environ["LLM_PROXY_ENABLE_CACHE"]
        del os.environ["LLM_PROXY_CACHE_MAX_SIZE"]

    print("✓ Environment override works")


def test_compression_strategies():
    """Test valid compression strategies."""
    _clear_llm_proxy_env()

    settings = _get_settings_without_env_file()

    # Default should be truncate_oldest
    assert settings.compression_strategy == "truncate_oldest"

    # Can be set to summarize_oldest
    os.environ["LLM_PROXY_COMPRESSION_STRATEGY"] = "summarize_oldest"
    try:
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.compression_strategy == "summarize_oldest"
    finally:
        del os.environ["LLM_PROXY_COMPRESSION_STRATEGY"]

    print("✓ Compression strategies work")


def test_kimi_code_compat():
    """Test Kimi Code compatibility settings."""
    settings = _get_settings_without_env_file()

    # Defaults
    assert settings.kimi_code_compat 
    assert settings.kimi_code_version == "1.0.0"
    assert settings.kimi_code_device_name == "kimi-proxy"

    # Override
    os.environ["LLM_PROXY_KIMI_CODE_COMPAT"] = "true"
    os.environ["LLM_PROXY_KIMI_CODE_VERSION"] = "2.0.0"

    try:
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.kimi_code_compat 
        assert settings.kimi_code_version == "2.0.0"
    finally:
        del os.environ["LLM_PROXY_KIMI_CODE_COMPAT"]
        del os.environ["LLM_PROXY_KIMI_CODE_VERSION"]

    print("✓ Kimi Code settings work")


def test_ollama_settings():
    """Test Ollama integration settings."""
    settings = _get_settings_without_env_file()

    # Defaults
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "llama3.2"
    assert settings.ollama_enable_compression 

    # Override
    os.environ["LLM_PROXY_OLLAMA_BASE_URL"] = "http://ollama:11434"
    os.environ["LLM_PROXY_OLLAMA_MODEL"] = "mistral"

    try:
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.ollama_base_url == "http://ollama:11434"
        assert settings.ollama_model == "mistral"
    finally:
        del os.environ["LLM_PROXY_OLLAMA_BASE_URL"]
        del os.environ["LLM_PROXY_OLLAMA_MODEL"]

    print("✓ Ollama settings work")


def test_filtering_settings():
    """Test message filtering settings."""
    settings = _get_settings_without_env_file()

    # Defaults
    assert settings.deduplicate_system_messages 
    assert settings.remove_empty_messages 
    assert settings.strip_base64_images 

    # Override
    os.environ["LLM_PROXY_DEDUPLICATE_SYSTEM_MESSAGES"] = "false"
    os.environ["LLM_PROXY_STRIP_BASE64_IMAGES"] = "true"

    try:
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.deduplicate_system_messages 
        assert settings.strip_base64_images 
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
        import importlib

        from llmproxy import config

        importlib.reload(config)
        settings = config.Settings()
        assert settings.port == 9000  # int
        assert settings.enable_cache   # bool
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
