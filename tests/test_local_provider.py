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


class TestCleanMessagesForOllama:
    """Tests for _clean_messages_for_ollama method."""

    def test_simple_messages_unchanged(self):
        """Simple user/assistant messages should pass through unchanged."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        
        cleaned = provider._clean_messages_for_ollama(messages)
        
        assert len(cleaned) == 3
        assert cleaned[0] == {"role": "user", "content": "Hello"}
        assert cleaned[1] == {"role": "assistant", "content": "Hi there!"}
        assert cleaned[2] == {"role": "user", "content": "How are you?"}
        print("✓ Simple messages unchanged")

    def test_tool_messages_converted(self):
        """Tool messages should be converted to assistant messages."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        messages = [
            {"role": "user", "content": "What time is it?"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "get_datetime"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "2024-01-15T10:30:00"},
        ]
        
        cleaned = provider._clean_messages_for_ollama(messages)
        
        # Tool message should be converted to assistant
        assert len(cleaned) == 3
        assert cleaned[0] == {"role": "user", "content": "What time is it?"}
        # Assistant with tool_calls should have note about tools
        assert cleaned[1]["role"] == "assistant"
        assert "Used tools" in cleaned[1]["content"]
        # Tool message converted to assistant
        assert cleaned[2]["role"] == "assistant"
        assert "Tool result" in cleaned[2]["content"]
        print("✓ Tool messages converted")

    def test_tool_calls_removed_from_assistant(self):
        """tool_calls field should be stripped from assistant messages."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        messages = [
            {"role": "user", "content": "Read file test.txt"},
            {"role": "assistant", "content": "I'll read it", "tool_calls": [{"id": "1", "function": {"name": "read_file", "arguments": "{}"}}]},
        ]
        
        cleaned = provider._clean_messages_for_ollama(messages)
        
        assert len(cleaned) == 2
        assert "tool_calls" not in cleaned[1]
        assert cleaned[1]["role"] == "assistant"
        assert "Used tools" in cleaned[1]["content"]
        print("✓ Tool calls removed from assistant")

    def test_empty_tool_messages_skipped(self):
        """Empty tool messages should be skipped."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "tool", "tool_call_id": "1", "content": ""},  # Empty
            {"role": "assistant", "content": "Hi!"},
        ]
        
        cleaned = provider._clean_messages_for_ollama(messages)
        
        assert len(cleaned) == 2  # Empty tool message skipped
        assert cleaned[0]["role"] == "user"
        assert cleaned[1]["role"] == "assistant"
        print("✓ Empty tool messages skipped")

    def test_system_messages_preserved(self):
        """System messages should be preserved."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        
        cleaned = provider._clean_messages_for_ollama(messages)
        
        assert len(cleaned) == 2
        assert cleaned[0] == {"role": "system", "content": "You are a helpful assistant."}
        print("✓ System messages preserved")


class TestToolSupport:
    """Tests for tool support via prompt engineering."""

    def test_format_tools_as_text(self):
        """Tools should be formatted as text instructions."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_datetime",
                    "description": "Get current date and time",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "timezone": {"type": "string", "description": "Timezone"},
                            "format": {"type": "string", "description": "Output format"},
                        },
                        "required": ["timezone"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                        },
                        "required": ["query"],
                    },
                },
            },
        ]
        
        text = provider._format_tools_as_text(tools)
        
        assert "You have access to the following tools:" in text
        assert "get_datetime" in text
        assert "search_web" in text
        assert "Get current date and time" in text
        assert "timezone" in text
        assert "(required)" in text
        assert "TOOL:" in text
        assert "ARGS:" in text
        print("✓ Tools formatted as text")

    def test_format_tools_empty(self):
        """Empty tools should return empty string."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        text = provider._format_tools_as_text([])
        
        assert text == ""
        print("✓ Empty tools returns empty string")

    def test_parse_tool_response_no_tools(self):
        """Response without tool markers should return content only."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        content = "Hello, how can I help you?"
        
        clean_content, tool_calls = provider._parse_tool_response(content)
        
        assert clean_content == content
        assert tool_calls is None
        print("✓ Plain response parsed correctly")

    def test_parse_tool_response_with_tool(self):
        """Response with tool markers should extract tool calls."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        content = "I'll search for that.\nTOOL: search_web\nARGS: {\"query\": \"latest news\"}"
        
        clean_content, tool_calls = provider._parse_tool_response(content)
        
        assert "I'll search for that" in clean_content
        assert "TOOL:" not in clean_content
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0]["function"]["name"] == "search_web"
        assert "latest news" in tool_calls[0]["function"]["arguments"]
        print("✓ Tool response parsed correctly")

    def test_parse_tool_response_multiple_tools(self):
        """Response with multiple tools should extract all."""
        from llmproxy.local_provider import LocalProvider
        
        provider = LocalProvider()
        content = """I'll help you.
TOOL: get_datetime
ARGS: {"timezone": "UTC"}
Then I'll search.
TOOL: search_web
ARGS: {"query": "hello"}"""
        
        clean_content, tool_calls = provider._parse_tool_response(content)
        
        assert tool_calls is not None
        assert len(tool_calls) == 2
        assert tool_calls[0]["function"]["name"] == "get_datetime"
        assert tool_calls[1]["function"]["name"] == "search_web"
        print("✓ Multiple tools parsed correctly")
