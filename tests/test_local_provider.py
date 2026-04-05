"""Tests for local LLM provider using Ollama."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from llmproxy.local_provider import (
    MODEL_ALIASES,
    RECOMMENDED_MODELS,
    LocalProvider,
    get_local_provider,
    reset_local_provider,
)


class TestModelAliases:
    """Test model alias resolution."""

    def test_all_aliases_defined(self):
        """All expected aliases are defined."""
        expected = [
            "local-coder",
            "local-coder-small",
            "local-coder-large",
            "local",
            "local-fast",
            "local-deepseek",
            "local-deepseek-large",
            "local-codellama",
            "local-codellama-small",
            "local-codellama-large",
        ]
        for alias in expected:
            assert alias in MODEL_ALIASES, f"Missing alias: {alias}"

    def test_alias_resolution_qwen(self):
        """Qwen model aliases resolve correctly."""
        provider = LocalProvider()
        assert provider._resolve_model("local-coder") == "qwen2.5-coder:14b"
        assert provider._resolve_model("local-coder-small") == "qwen2.5-coder:7b"
        assert provider._resolve_model("local-coder-large") == "qwen2.5-coder:32b"

    def test_alias_resolution_deepseek(self):
        """DeepSeek model aliases resolve correctly."""
        provider = LocalProvider()
        assert provider._resolve_model("local-deepseek") == "deepseek-coder:6.7b"
        assert provider._resolve_model("local-deepseek-large") == "deepseek-coder:33b"

    def test_alias_resolution_codellama(self):
        """CodeLlama model aliases resolve correctly."""
        provider = LocalProvider()
        assert provider._resolve_model("local-codellama") == "codellama:13b"
        assert provider._resolve_model("local-codellama-small") == "codellama:7b"
        assert provider._resolve_model("local-codellama-large") == "codellama:34b"

    def test_alias_resolution_llama(self):
        """Llama model aliases resolve correctly."""
        provider = LocalProvider()
        assert provider._resolve_model("local") == "llama3.3:latest"
        assert provider._resolve_model("local-fast") == "llama3.2:3b"

    def test_direct_model_passthrough(self):
        """Direct model names are passed through unchanged."""
        provider = LocalProvider()
        assert provider._resolve_model("custom-model:7b") == "custom-model:7b"
        assert provider._resolve_model("qwen2.5-coder:14b") == "qwen2.5-coder:14b"


class TestLocalProviderInit:
    """Test LocalProvider initialization."""

    def test_default_base_url(self):
        """Default base URL is localhost."""
        provider = LocalProvider()
        assert provider.base_url == "http://localhost:11434"

    def test_custom_base_url(self):
        """Custom base URL is respected."""
        provider = LocalProvider(base_url="http://ollama:11434")
        assert provider.base_url == "http://ollama:11434"

    def test_custom_timeout(self):
        """Custom timeout is respected."""
        provider = LocalProvider(timeout=300.0)
        assert provider.timeout == 300.0

    def test_client_lazy_init(self):
        """HTTP client is created lazily."""
        provider = LocalProvider()
        assert provider._client is None


class TestRecommendedModels:
    """Test recommended models structure."""

    def test_all_recommended_have_required_fields(self):
        """All recommended models have required info fields."""
        required_fields = ["description", "vram_gb", "strengths"]
        for model, info in RECOMMENDED_MODELS.items():
            for field in required_fields:
                assert field in info, f"Model {model} missing field: {field}"
            assert isinstance(info["vram_gb"], int)
            assert isinstance(info["strengths"], list)

    def test_vram_requirements_reasonable(self):
        """VRAM requirements are reasonable values."""
        for model, info in RECOMMENDED_MODELS.items():
            assert 4 <= info["vram_gb"] <= 64, f"VRAM for {model} seems unreasonable"


class TestGlobalProvider:
    """Test global provider instance."""

    def test_get_local_provider_creates_instance(self):
        """get_local_provider creates an instance."""
        reset_local_provider()
        provider = get_local_provider()
        assert isinstance(provider, LocalProvider)
        assert provider.base_url == "http://localhost:11434"

    def test_get_local_provider_returns_same_instance(self):
        """get_local_provider returns the same instance."""
        reset_local_provider()
        provider1 = get_local_provider()
        provider2 = get_local_provider()
        assert provider1 is provider2

    def test_reset_local_provider(self):
        """reset_local_provider clears the instance."""
        reset_local_provider()
        provider1 = get_local_provider()
        reset_local_provider()
        provider2 = get_local_provider()
        assert provider1 is not provider2


@pytest.mark.asyncio
class TestLocalProviderAsync:
    """Test async LocalProvider methods."""

    async def test_is_available_false_when_no_ollama(self):
        """is_available returns False when Ollama is not running."""
        provider = LocalProvider(base_url="http://localhost:59999")  # Wrong port
        result = await provider.is_available()
        assert result is False

    async def test_chat_completions_model_not_found(self):
        """chat_completions raises proper error for missing model."""
        provider = LocalProvider(base_url="http://localhost:59999")
        
        with pytest.raises(Exception) as exc_info:
            await provider.chat_completions(
                model="nonexistent-model",
                messages=[{"role": "user", "content": "Hello"}],
            )
        
        assert "Cannot connect to Ollama" in str(exc_info.value)

    async def test_list_models_raises_when_no_ollama(self):
        """list_models raises HTTPException when Ollama is not running."""
        provider = LocalProvider(base_url="http://localhost:59999")
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await provider.list_models()
        
        assert exc_info.value.status_code == 503

    async def test_aclose_closes_client(self):
        """aclose properly closes the HTTP client."""
        provider = LocalProvider()
        # Force client creation
        await provider._get_client()
        assert provider._client is not None
        
        await provider.aclose()
        assert provider._client is None


class TestOpenAICompatibility:
    """Test OpenAI-compatible response format."""

    def test_chat_response_structure(self):
        """Chat response has OpenAI-compatible structure."""
        # Mock response data
        mock_response = {
            "id": "chatcmpl-test123",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "qwen2.5-coder:14b",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello!",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
        
        # Verify structure
        assert "id" in mock_response
        assert "object" in mock_response
        assert "created" in mock_response
        assert "model" in mock_response
        assert "choices" in mock_response
        assert "usage" in mock_response
        assert len(mock_response["choices"]) == 1
        assert mock_response["choices"][0]["message"]["role"] == "assistant"

    def test_embeddings_response_structure(self):
        """Embeddings response has OpenAI-compatible structure."""
        mock_response = {
            "object": "list",
            "data": [
                {
                    "object": "embedding",
                    "embedding": [0.1, 0.2, 0.3],
                    "index": 0,
                }
            ],
            "model": "qwen2.5-coder:14b",
            "usage": {
                "prompt_tokens": 10,
                "total_tokens": 10,
            },
        }
        
        assert mock_response["object"] == "list"
        assert len(mock_response["data"]) == 1
        assert mock_response["data"][0]["object"] == "embedding"
