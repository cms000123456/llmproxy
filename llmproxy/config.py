from __future__ import annotations

"""Configuration for LLM Proxy."""

from typing import Any, Dict, List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Upstream API (Control - primary upstream)
    upstream_base_url: str = "https://api.moonshot.cn/v1"
    upstream_api_key: str = ""

    # A/B Testing Configuration
    ab_test_enabled: bool = False  # Enable A/B testing between control and experimental upstreams
    experimental_upstream_base_url: str = (
        ""  # Experimental upstream URL (e.g., different model/version)
    )
    experimental_upstream_api_key: str = ""  # Optional separate API key for experimental
    ab_test_traffic_split: float = 0.1  # Fraction of traffic to route to experimental (0.0 to 1.0)
    ab_test_sticky_sessions: bool = True  # Route same client to same variant (based on API key)

    # Proxy server
    host: str = "0.0.0.0"
    port: int = 8080

    # Authentication
    api_keys: List[str] = []  # List of valid API keys for client authentication
    auth_enabled: bool = True  # Enable/disable API key authentication

    # Filtering
    enable_filtering: bool = True
    max_message_length: int = 32000  # truncate individual messages longer than this
    strip_base64_images: bool = False  # remove image content blocks entirely
    deduplicate_system_messages: bool = True
    remove_empty_messages: bool = True

    # Compression
    enable_compression: bool = True
    compression_strategy: str = "truncate_oldest"  # or "summarize_oldest"
    max_total_tokens: int = 120000  # target token budget for the full prompt
    summary_model: str = "moonshot-v1-8k"  # cheaper model for summarization

    # Ollama local LLM integration
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""  # Optional API key for Ollama (if behind auth proxy)
    ollama_model: str = "llama3.2"  # lightweight model for local grunt work
    ollama_enable_compression: bool = True  # use Ollama to summarize old context
    ollama_enable_relevance_filter: bool = False  # drop low-relevance older messages via Ollama
    ollama_relevance_threshold: float = 0.5  # keep messages scored >= this (0-1)

    # Caching
    enable_cache: bool = True
    cache_backend: str = "memory"  # "memory" or "redis"
    cache_ttl_seconds: int = 300
    cache_max_size: int = 1000

    # Redis configuration (when cache_backend="redis")
    redis_url: str = "redis://localhost:6379"
    redis_key_prefix: str = "llmproxy:"

    # Retry configuration
    max_retries: int = 3  # Number of retries for upstream requests
    retry_backoff: float = 2.0  # Exponential backoff base (seconds)
    retry_max_wait: float = 60.0  # Maximum wait time between retries

    # Kimi Code compatibility
    kimi_code_compat: bool = False  # inject Kimi Code agent headers
    kimi_code_version: str = "1.0.0"
    kimi_code_device_name: str = "kimi-proxy"
    kimi_code_device_id: str = ""

    # Logging configuration
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_format: str = "console"  # "console" (colored) or "json" (structured)

    # Cost tracking
    enable_cost_tracking: bool = True
    cost_upstream_price: float = 0.01  # $ per 1K tokens
    cost_downstream_price: float = 0.03  # $ per 1K tokens
    cost_storage_path: str = "data/cost_tracker.json"

    # Prompt templates configuration
    prompt_templates: Dict[str, Dict[str, Any]] = {}  # Custom templates to register

    class Config:
        env_prefix = "LLM_PROXY_"
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars not defined in Settings


settings = Settings()
